#!/usr/bin/env python3
"""Export a checksum-sealed, path-redacted run evidence bundle.

The bundle intentionally contains only the finalized manifest, preflight,
summary, and per-trial verdict documents. Agent transcripts and candidate
sandboxes remain in the private source run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import aggregate


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _selected_files(source: Path) -> list[Path]:
    required = [source / name for name in ("manifest.json", "preflight.json", "summary.json")]
    verdicts = sorted((source / "trials").glob("*/*/trial_*/verdict.json"))
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"source run is missing required files: {missing}")
    if not verdicts:
        raise ValueError("source run has no verdict documents")
    return required + verdicts


def _redact(data: bytes, replacements: list[tuple[bytes, bytes]]) -> bytes:
    for original, replacement in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if not original or original == replacement:
            raise ValueError("redaction prefixes must be non-empty and distinct")
        data = data.replace(original, replacement)
    return data


def export_bundle(source: Path, destination_root: Path, repo_root: Path, home: Path) -> Path:
    source = source.resolve()
    destination_root = destination_root.resolve()
    repo_root = repo_root.resolve()
    home = home.resolve()
    aggregate.verify_checksums(source)

    destination = destination_root / source.name
    original_digest_path = destination_root / f"{source.name}.original-digests.json"
    if destination.exists() or original_digest_path.exists():
        raise ValueError(f"destination already exists for run {source.name}")

    files = _selected_files(source)
    replacements = [
        (str(repo_root).encode("utf-8"), b"/REPO"),
        (str(home).encode("utf-8"), b"/HOME"),
    ]
    original_digests: dict[str, str] = {}
    redacted_digests: dict[str, str] = {}
    destination.mkdir(parents=True)
    for path in files:
        relative = path.relative_to(source)
        original = path.read_bytes()
        redacted = _redact(original, replacements)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(redacted)
        key = relative.as_posix()
        original_digests[key] = _sha256(original)
        redacted_digests[key] = _sha256(redacted)

    checksum_document = {"algorithm": "sha256", "files": redacted_digests}
    (destination / "checksums.sha256").write_text(
        json.dumps(checksum_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original_document = {
        "algorithm": "sha256",
        "files": original_digests,
        "note": "pre-redaction digests; two path prefixes (/REPO,/HOME) redacted in committed files",
        "redaction": {
            "effect": "Only absolute repository-root and home-directory prefixes were replaced.",
            "replacement_labels": ["/REPO", "/HOME"],
        },
    }
    original_digest_path.write_text(
        json.dumps(original_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    aggregate.verify_checksums(destination)
    aggregate.aggregate_run(destination)
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--destination-root", default=Path("evidence/runs"), type=Path)
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--home", default=Path.home(), type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        destination = export_bundle(
            args.source_run,
            args.destination_root,
            args.repo_root,
            args.home,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"evidence export error: {exc}")
        return 2
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
