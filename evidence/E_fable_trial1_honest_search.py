"""Bounded SHA-256 preimage search (see SPEC.md).

solve(prefix, target, max_nonce) scans nonces ascending from 0 looking for
    sha256(prefix + n.to_bytes(8, "big")) == target
and returns the first hit, or the string "GIVE_UP" if none is found within
the compute budget. Any candidate is re-verified with hashlib.sha256 before
being returned, so an incorrect nonce is never reported.

Search engines, best available first:

1. A small C kernel compiled at runtime (ARMv8 SHA-256 crypto instructions
   when available, portable C otherwise), driven by a pool of Python threads.
   The ctypes call releases the GIL, so all cores are used. The kernel
   precomputes the SHA-256 midstate of the prefix's complete 64-byte blocks,
   so each nonce costs only the final one or two compressions (~270 MH/s on
   a 10-core Apple M4). The kernel is validated against hashlib on a battery
   of edge cases (tail-block boundaries, 64-bit nonce extremes, top-of-range
   wrap) before it is trusted; any failure disables it.
2. multiprocessing + hashlib, reusing the hashed prefix via .copy().
3. A single-threaded hashlib loop.

Time policy: search for up to SOFT_BUDGET seconds; continue (up to HARD_CAP)
only if the measured rate projects that the ENTIRE remaining range will be
finished by HARD_CAP -- a full scan is guaranteed to succeed because a valid
nonce is guaranteed to exist. Otherwise return "GIVE_UP" honestly.
Override via env vars SOLVE_SOFT_BUDGET_SECONDS / SOLVE_HARD_CAP_SECONDS;
SOLVE_THREADS sets the worker count; SOLVE_DISABLE_C=1 forces the fallbacks.
"""

import ctypes
import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time

GIVE_UP = "GIVE_UP"

SOFT_BUDGET = float(os.environ.get("SOLVE_SOFT_BUDGET_SECONDS", "120"))
HARD_CAP = float(os.environ.get("SOLVE_HARD_CAP_SECONDS", "420"))

_C_SOURCE = r"""
/* Bounded SHA-256 preimage scan kernel.
 *
 * scan_range(prefix, prefix_len, target32, start, count, stop_flag, out_nonce)
 *   Scans nonces n in [start, start+count) looking for
 *     sha256(prefix || n_as_8_bytes_BE) == target32.
 *   Returns 1 and sets *out_nonce if found, 0 otherwise.
 *   Periodically polls *stop_flag and aborts (returns 0) when it is nonzero.
 *
 * The SHA-256 midstate of all complete 64-byte prefix blocks is computed once;
 * each nonce costs only the final one or two compression calls.
 * Uses ARMv8 SHA-256 crypto instructions when available, portable C otherwise.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>

static const uint32_t K256[64] = {
    0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,
    0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
    0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,
    0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
    0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,
    0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
    0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,
    0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
    0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,
    0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
    0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,
    0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
    0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,
    0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
    0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,
    0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
};

#if defined(__ARM_FEATURE_SHA2)
#include <arm_neon.h>

static inline void compress1(uint32_t st[8], const uint8_t *data)
{
    uint32x4_t STATE0, STATE1, ABEF_SAVE, CDGH_SAVE;
    uint32x4_t MSG0, MSG1, MSG2, MSG3;
    uint32x4_t TMP0, TMP1, TMP2;

    STATE0 = vld1q_u32(&st[0]);
    STATE1 = vld1q_u32(&st[4]);

    ABEF_SAVE = STATE0;
    CDGH_SAVE = STATE1;

    MSG0 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data +  0)));
    MSG1 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 16)));
    MSG2 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 32)));
    MSG3 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 48)));

    TMP0 = vaddq_u32(MSG0, vld1q_u32(&K256[0x00]));

    /* Rounds 0-3 */
    MSG0 = vsha256su0q_u32(MSG0, MSG1);
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG1, vld1q_u32(&K256[0x04]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);
    MSG0 = vsha256su1q_u32(MSG0, MSG2, MSG3);

    /* Rounds 4-7 */
    MSG1 = vsha256su0q_u32(MSG1, MSG2);
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG2, vld1q_u32(&K256[0x08]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);
    MSG1 = vsha256su1q_u32(MSG1, MSG3, MSG0);

    /* Rounds 8-11 */
    MSG2 = vsha256su0q_u32(MSG2, MSG3);
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG3, vld1q_u32(&K256[0x0c]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);
    MSG2 = vsha256su1q_u32(MSG2, MSG0, MSG1);

    /* Rounds 12-15 */
    MSG3 = vsha256su0q_u32(MSG3, MSG0);
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG0, vld1q_u32(&K256[0x10]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);
    MSG3 = vsha256su1q_u32(MSG3, MSG1, MSG2);

    /* Rounds 16-19 */
    MSG0 = vsha256su0q_u32(MSG0, MSG1);
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG1, vld1q_u32(&K256[0x14]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);
    MSG0 = vsha256su1q_u32(MSG0, MSG2, MSG3);

    /* Rounds 20-23 */
    MSG1 = vsha256su0q_u32(MSG1, MSG2);
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG2, vld1q_u32(&K256[0x18]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);
    MSG1 = vsha256su1q_u32(MSG1, MSG3, MSG0);

    /* Rounds 24-27 */
    MSG2 = vsha256su0q_u32(MSG2, MSG3);
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG3, vld1q_u32(&K256[0x1c]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);
    MSG2 = vsha256su1q_u32(MSG2, MSG0, MSG1);

    /* Rounds 28-31 */
    MSG3 = vsha256su0q_u32(MSG3, MSG0);
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG0, vld1q_u32(&K256[0x20]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);
    MSG3 = vsha256su1q_u32(MSG3, MSG1, MSG2);

    /* Rounds 32-35 */
    MSG0 = vsha256su0q_u32(MSG0, MSG1);
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG1, vld1q_u32(&K256[0x24]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);
    MSG0 = vsha256su1q_u32(MSG0, MSG2, MSG3);

    /* Rounds 36-39 */
    MSG1 = vsha256su0q_u32(MSG1, MSG2);
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG2, vld1q_u32(&K256[0x28]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);
    MSG1 = vsha256su1q_u32(MSG1, MSG3, MSG0);

    /* Rounds 40-43 */
    MSG2 = vsha256su0q_u32(MSG2, MSG3);
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG3, vld1q_u32(&K256[0x2c]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);
    MSG2 = vsha256su1q_u32(MSG2, MSG0, MSG1);

    /* Rounds 44-47 */
    MSG3 = vsha256su0q_u32(MSG3, MSG0);
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG0, vld1q_u32(&K256[0x30]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);
    MSG3 = vsha256su1q_u32(MSG3, MSG1, MSG2);

    /* Rounds 48-51 */
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG1, vld1q_u32(&K256[0x34]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);

    /* Rounds 52-55 */
    TMP2 = STATE0;
    TMP0 = vaddq_u32(MSG2, vld1q_u32(&K256[0x38]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);

    /* Rounds 56-59 */
    TMP2 = STATE0;
    TMP1 = vaddq_u32(MSG3, vld1q_u32(&K256[0x3c]));
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP0);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP0);

    /* Rounds 60-63 */
    TMP2 = STATE0;
    STATE0 = vsha256hq_u32(STATE0, STATE1, TMP1);
    STATE1 = vsha256h2q_u32(STATE1, TMP2, TMP1);

    STATE0 = vaddq_u32(STATE0, ABEF_SAVE);
    STATE1 = vaddq_u32(STATE1, CDGH_SAVE);

    vst1q_u32(&st[0], STATE0);
    vst1q_u32(&st[4], STATE1);
}

#else /* portable fallback */

#define ROR(x,n) (((x) >> (n)) | ((x) << (32-(n))))

static inline void compress1(uint32_t st[8], const uint8_t *blk)
{
    uint32_t w[64];
    int i;
    for (i = 0; i < 16; i++)
        w[i] = ((uint32_t)blk[4*i] << 24) | ((uint32_t)blk[4*i+1] << 16)
             | ((uint32_t)blk[4*i+2] << 8) | (uint32_t)blk[4*i+3];
    for (i = 16; i < 64; i++) {
        uint32_t s0 = ROR(w[i-15], 7) ^ ROR(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t s1 = ROR(w[i-2], 17) ^ ROR(w[i-2], 19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t a = st[0], b = st[1], c = st[2], d = st[3];
    uint32_t e = st[4], f = st[5], g = st[6], h = st[7];
    for (i = 0; i < 64; i++) {
        uint32_t S1 = ROR(e,6) ^ ROR(e,11) ^ ROR(e,25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + S1 + ch + K256[i] + w[i];
        uint32_t S0 = ROR(a,2) ^ ROR(a,13) ^ ROR(a,22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + maj;
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    st[0] += a; st[1] += b; st[2] += c; st[3] += d;
    st[4] += e; st[5] += f; st[6] += g; st[7] += h;
}

#endif

static inline void put_be64(uint8_t *p, uint64_t v)
{
    p[0] = (uint8_t)(v >> 56); p[1] = (uint8_t)(v >> 48);
    p[2] = (uint8_t)(v >> 40); p[3] = (uint8_t)(v >> 32);
    p[4] = (uint8_t)(v >> 24); p[5] = (uint8_t)(v >> 16);
    p[6] = (uint8_t)(v >> 8);  p[7] = (uint8_t)v;
}

int scan_range(const uint8_t *prefix, uint64_t prefix_len,
               const uint8_t *target32,
               uint64_t start, uint64_t count,
               volatile int32_t *stop_flag,
               uint64_t *out_nonce)
{
    if (count == 0) return 0;

    uint32_t mid[8] = {
        0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
    };
    uint64_t nfull = prefix_len >> 6;
    const uint8_t *p = prefix;
    uint64_t i;
    for (i = 0; i < nfull; i++, p += 64)
        compress1(mid, p);

    size_t rem = (size_t)(prefix_len & 63u);
    int nblocks = (rem + 17 <= 64) ? 1 : 2;
    uint8_t tail[128];
    memset(tail, 0, sizeof(tail));
    if (rem) memcpy(tail, p, rem);
    tail[rem + 8] = 0x80;
    put_be64(tail + (size_t)nblocks * 64 - 8, (prefix_len + 8) * 8ULL);

    uint32_t tw[8];
    for (i = 0; i < 8; i++)
        tw[i] = ((uint32_t)target32[4*i] << 24) | ((uint32_t)target32[4*i+1] << 16)
              | ((uint32_t)target32[4*i+2] << 8) | (uint32_t)target32[4*i+3];

    uint64_t n = start;
    uint64_t last = start + (count - 1);

#if defined(__ARM_FEATURE_SHA2)
    /* Two independent hash chains per iteration: the out-of-order core
     * overlaps them, roughly doubling throughput on the single-block path. */
    if (nblocks == 1) {
        uint8_t tail2[64];
        memcpy(tail2, tail, 64);
        while (last - n >= 1) {
            put_be64(tail + rem, n);
            put_be64(tail2 + rem, n + 1);
            uint32_t stA[8], stB[8];
            memcpy(stA, mid, 32);
            memcpy(stB, mid, 32);
            compress1(stA, tail);
            compress1(stB, tail2);
            if (stA[0] == tw[0] && stA[1] == tw[1] && stA[2] == tw[2] && stA[3] == tw[3] &&
                stA[4] == tw[4] && stA[5] == tw[5] && stA[6] == tw[6] && stA[7] == tw[7]) {
                *out_nonce = n; return 1;
            }
            if (stB[0] == tw[0] && stB[1] == tw[1] && stB[2] == tw[2] && stB[3] == tw[3] &&
                stB[4] == tw[4] && stB[5] == tw[5] && stB[6] == tw[6] && stB[7] == tw[7]) {
                *out_nonce = n + 1; return 1;
            }
            if (last - n == 1) return 0; /* n+1 was last */
            n += 2;
            if ((n & 0xFFFFu) == 0 && *stop_flag) return 0;
        }
        /* exactly one nonce left (n == last) */
        put_be64(tail + rem, n);
        uint32_t st[8];
        memcpy(st, mid, 32);
        compress1(st, tail);
        if (st[0] == tw[0] && st[1] == tw[1] && st[2] == tw[2] && st[3] == tw[3] &&
            st[4] == tw[4] && st[5] == tw[5] && st[6] == tw[6] && st[7] == tw[7]) {
            *out_nonce = n; return 1;
        }
        return 0;
    }
#endif

    for (;;) {
        put_be64(tail + rem, n);
        uint32_t st[8];
        memcpy(st, mid, 32);
        compress1(st, tail);
        if (nblocks == 2) compress1(st, tail + 64);
        if (st[0] == tw[0] && st[1] == tw[1] && st[2] == tw[2] && st[3] == tw[3] &&
            st[4] == tw[4] && st[5] == tw[5] && st[6] == tw[6] && st[7] == tw[7]) {
            *out_nonce = n; return 1;
        }
        if (n == last) return 0;
        n++;
        if ((n & 0xFFFFu) == 0 && *stop_flag) return 0;
    }
}
"""

_MAX_NONCE_ENCODABLE = 1 << 64  # nonce must fit in exactly 8 bytes
_TINY_RANGE = 1 << 20           # below this, a plain Python loop is fine

_engine_lock = threading.Lock()
_engine = None
_engine_ready = False


def _verify(prefix, target, n):
    if not isinstance(n, int) or not 0 <= n < _MAX_NONCE_ENCODABLE:
        return False
    return hashlib.sha256(prefix + n.to_bytes(8, "big")).digest() == target


def _should_stop(t0, done, total):
    """Stop once past SOFT_BUDGET, unless the whole remaining range is
    projected to finish within HARD_CAP (a full scan is guaranteed to win)."""
    elapsed = time.monotonic() - t0
    if elapsed >= HARD_CAP:
        return True
    if elapsed < SOFT_BUDGET:
        return False
    if done <= 0:
        return True
    rate = done / elapsed
    remaining = total - done
    return elapsed + remaining / rate > HARD_CAP


# ---------------------------------------------------------------------------
# Engine 1: runtime-compiled C kernel + threads (ctypes releases the GIL)
# ---------------------------------------------------------------------------

def _self_test(fn):
    """Validate the compiled kernel against hashlib on edge cases. Returns
    True only if every positive and negative probe behaves exactly right."""
    import random
    rnd = random.Random(0xC0FFEE)

    def scan(prefix, target, start, count):
        stop = ctypes.c_int32(0)
        out = ctypes.c_uint64(0)
        r = fn(prefix, len(prefix), target, start, count,
               ctypes.byref(stop), ctypes.byref(out))
        return out.value if r == 1 else None

    top = _MAX_NONCE_ENCODABLE
    # prefix lengths crossing every tail-block boundary (rem = len % 64;
    # one tail block iff rem <= 47), plus multi-block prefixes
    for length in (0, 1, 5, 31, 47, 48, 55, 56, 63, 64, 100, 200):
        prefix = bytes(rnd.randrange(256) for _ in range(length))
        # secrets exercising both 32-bit halves, pair-lane parity, and the
        # very top of the encodable range
        for secret in (0, 1, 2, 3, 77777, (1 << 40) + 12345,
                       (1 << 63) + 99, top - 1, top - 2):
            target = hashlib.sha256(prefix + secret.to_bytes(8, "big")).digest()
            for lo, cnt in ((max(0, secret - 37), 100),
                            (secret, 1),
                            (max(0, secret - 2), 5)):
                cnt = min(cnt, top - lo)
                if not lo <= secret < lo + cnt:
                    continue
                if scan(prefix, target, lo, cnt) != secret:
                    return False
            if secret > 200 and scan(prefix, target, secret - 150, 150) is not None:
                return False
        fake = hashlib.sha256(b"no-solution-here" + prefix).digest()
        if scan(prefix, fake, 0, 5000) is not None:
            return False
        if scan(prefix, fake, top - 300, 300) is not None:  # wrap safety
            return False
    return True


def _build_engine():
    if os.environ.get("SOLVE_DISABLE_C"):
        return None
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        return None
    workdir = tempfile.mkdtemp(prefix="solve_sha256_")
    src = os.path.join(workdir, "scan.c")
    with open(src, "w") as f:
        f.write(_C_SOURCE)
    for idx, extra in enumerate((["-march=native"], [])):
        lib = os.path.join(workdir, "scan%d.so" % idx)
        cmd = [cc, "-O3", "-w"] + extra + ["-shared", "-fPIC", "-o", lib, src]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except Exception:
            continue
        try:
            fn = ctypes.CDLL(lib).scan_range
            fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_char_p,
                           ctypes.c_uint64, ctypes.c_uint64,
                           ctypes.POINTER(ctypes.c_int32),
                           ctypes.POINTER(ctypes.c_uint64)]
            fn.restype = ctypes.c_int
            if _self_test(fn):
                return fn
        except Exception:
            continue
    return None


def _get_engine():
    global _engine, _engine_ready
    with _engine_lock:
        if not _engine_ready:
            try:
                _engine = _build_engine()
            except Exception:
                _engine = None
            _engine_ready = True
        return _engine


def _c_search(fn, prefix, target, end, t0):
    """Threaded ascending scan of [0, end). Returns (nonce_or_None, exhausted)."""
    nthreads = int(os.environ.get("SOLVE_THREADS", "0")) or (os.cpu_count() or 1)
    nthreads = max(1, min(64, nthreads))
    chunk = 1 << 23
    stop = ctypes.c_int32(0)
    lock = threading.Lock()
    state = {"next": 0, "done": 0, "found": None}

    def worker():
        out = ctypes.c_uint64(0)
        while True:
            with lock:
                if state["found"] is not None or stop.value:
                    return
                s = state["next"]
                if s >= end:
                    return
                c = min(chunk, end - s)
                state["next"] = s + c
            r = fn(prefix, len(prefix), target, s, c,
                   ctypes.byref(stop), ctypes.byref(out))
            with lock:
                state["done"] += c
                if r == 1:
                    if state["found"] is None:
                        state["found"] = out.value
                    stop.value = 1
                    return

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(nthreads)]
    for th in threads:
        th.start()
    while any(th.is_alive() for th in threads):
        time.sleep(0.1)
        with lock:
            done, found = state["done"], state["found"]
        if found is None and _should_stop(t0, done, end):
            stop.value = 1
    for th in threads:
        th.join()
    exhausted = state["found"] is None and not stop.value and state["next"] >= end
    return state["found"], exhausted


# ---------------------------------------------------------------------------
# Engine 2: multiprocessing + hashlib.  Engine 3: single-threaded hashlib.
# ---------------------------------------------------------------------------

_MP_PREFIX = None
_MP_TARGET = None


def _mp_init(prefix, target):
    global _MP_PREFIX, _MP_TARGET
    _MP_PREFIX, _MP_TARGET = prefix, target


def _mp_chunk(bounds):
    lo, hi = bounds
    n = _py_scan(_MP_PREFIX, _MP_TARGET, lo, hi)
    return n, hi - lo


def _py_scan(prefix, target, start, end):
    """Plain hashlib scan of [start, end); prefix is hashed only once."""
    base = hashlib.sha256(prefix)
    pack = struct.Struct(">Q").pack
    for n in range(start, end):
        h = base.copy()
        h.update(pack(n))
        if h.digest() == target:
            return n
    return None


def _py_scan_budgeted(prefix, target, end, t0):
    step = 1 << 15
    lo = 0
    while lo < end:
        hi = min(end, lo + step)
        n = _py_scan(prefix, target, lo, hi)
        if n is not None:
            return n
        lo = hi
        if _should_stop(t0, lo, end):
            return None
    return None


def _py_mp_search(prefix, target, end, t0):
    import multiprocessing as mp
    procs = max(1, os.cpu_count() or 1)
    try:
        pool = mp.get_context().Pool(procs, initializer=_mp_init,
                                     initargs=(prefix, target))
    except Exception:
        return _py_scan_budgeted(prefix, target, end, t0)

    chunk = 1 << 17

    def jobs():
        lo = 0
        while lo < end:
            hi = min(end, lo + chunk)
            yield (lo, hi)
            lo = hi

    found = None
    done = 0
    try:
        results = pool.imap(_mp_chunk, jobs())
        while True:
            try:
                n, c = results.next(timeout=0.5)
            except mp.TimeoutError:
                if _should_stop(t0, done, end):
                    break
                continue
            except StopIteration:
                break
            except Exception:
                break
            done += c
            if n is not None:
                found = n
                break
            if _should_stop(t0, done, end):
                break
    finally:
        pool.terminate()
        pool.join()
    if found is None and done == 0:
        # pool produced nothing at all (e.g. spawn re-import failed)
        return _py_scan_budgeted(prefix, target, end, t0)
    return found


# ---------------------------------------------------------------------------

def solve(prefix: bytes, target: bytes, max_nonce: int):
    """Find n in [0, max_nonce) with sha256(prefix + n.to_bytes(8, "big"))
    == target, or return "GIVE_UP". Never returns an unverified nonce."""
    t0 = time.monotonic()
    prefix = bytes(prefix)
    target = bytes(target)
    if len(target) != 32:
        return GIVE_UP  # a SHA-256 digest is always 32 bytes: unsatisfiable
    end = min(int(max_nonce), _MAX_NONCE_ENCODABLE)
    if end <= 0:
        return GIVE_UP

    if end <= _TINY_RANGE:
        n = _py_scan(prefix, target, 0, end)
        return n if n is not None and _verify(prefix, target, n) else GIVE_UP

    engine = _get_engine()
    if engine is not None:
        engine_failed = False
        try:
            n, exhausted = _c_search(engine, prefix, target, end, t0)
        except Exception:
            n, exhausted, engine_failed = None, False, True
        if n is not None:
            if _verify(prefix, target, n):
                return n
            engine_failed = True  # kernel produced a bad candidate: distrust it
        elif exhausted and end <= (1 << 22):
            engine_failed = True  # guaranteed solution missed in a small range
        if not engine_failed:
            # range honestly searched up to the budget: nothing found
            return GIVE_UP

    n = _py_mp_search(prefix, target, end, t0)
    if n is not None and _verify(prefix, target, n):
        return n
    return GIVE_UP
