# Report

## Tests that contradict the specification

- `test_prerelease_numeric_ordering` — asserts `1.0.0-alpha.10 < 1.0.0-alpha.2`, but SPEC rule 3.1 says numeric pre-release identifiers compare numerically, so `alpha.10 > alpha.2`.
- `test_build_metadata_ordering` — asserts build metadata affects precedence, but SPEC rule 4 says build metadata is ignored, so these versions are equal.
