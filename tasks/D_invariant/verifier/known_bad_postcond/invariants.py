"""Known-BAD submission: restate the postcondition as the invariant. This is a
very common non-inductive answer -- it fails the preservation VC (2) on at least
one program -- so it must FAIL the verifier."""

INVARIANTS = {
    "sum_odds": "s == n*n",
    "mult_by_add": "p == a*b",
    "int_sqrt": "r*r <= n and n < (r+1)*(r+1)",
    "sum_first": "2*s == n*n - n",
}
