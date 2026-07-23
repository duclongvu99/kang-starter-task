"""Reference (correct) inductive invariants. Used only by the grader-validity gate."""

INVARIANTS = {
    "sum_odds": "0 <= i and i <= n and s == i*i",
    "mult_by_add": "0 <= i and i <= a and p == i*b",
    "int_sqrt": "0 <= r and r*r <= n",
    "sum_first": "0 <= i and i <= n and 2*s == i*i - i",
}
