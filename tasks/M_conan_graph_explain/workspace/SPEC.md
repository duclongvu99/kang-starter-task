# Task M — Implement `conan graph explain`

Add a production-quality `conan graph explain` command to this real Conan
snapshot. It must reconstruct a consumer dependency graph, identify a missing
binary, search local and selected remote configurations, rank the closest
binaries, and explain the differences in text and JSON.

This task is derived from the public Conan feature implemented upstream in PR
14694. Do not search for, fetch, or copy the upstream patch; implement from this
specification and the local codebase. Do not edit files below `conans/test/`.

## CLI and graph integration

1. Add the `graph explain` subcommand with the common graph arguments plus
   `--check-updates`, `--build-require`, and optional `--missing PATTERN`.
2. Resolve paths, remotes, lockfile overrides, host/build profiles, consumer or
   `--requires`/`--tool-requires` graphs exactly as `graph info` does. Analyze
   binaries without trying to install them.
3. Select the first missing node in graph order that matches `--missing` (or the
   first missing node if omitted). If none exists, raise `ConanException` with
   `There is no missing binary`.
4. Existing missing-binary guidance must mention all three options: listing
   available packages, replacing install with `conan graph explain`, and local
   source builds. Preserve singular/multiple missing-package behavior.

## Distance model and selection

For the selected reference, obtain package configurations from the local cache
and every enabled remote. A remote failure must not discard local/other-remote
results.

For each candidate compare its binary info with the expected `conaninfo`:

- `os` and `arch` differences are `platform` differences;
- all other settings differences are `settings` differences;
- option differences are `options` differences;
- requirements are matched by recipe name, and missing or unequal references
  are `dependencies` differences.

Each category serializes `expected` and `existing` lists. Rank candidates by the
lexicographic tuple `(number of platform differences, number of settings
differences, number of option differences, number of dependency differences)`.
Return every candidate tied at the single best distance and no worse candidate.
Exact matches therefore win over every non-exact match.

Use these exact explanation strings:

- platform: `This binary belongs to another OS or Architecture, highly incompatible.`
- settings: `This binary was built with different settings.`
- options: `This binary was built with the same settings, but different options`
- dependencies: `This binary has same settings and options, but different dependencies`
- exact: `This binary is an exact match for the defined inputs`

Include each candidate's source as `Local Cache` or its remote name.

## Formatting and API behavior

1. Add an API method on `ListAPI` that returns a `PackagesList` carrying normal
   configuration data plus `diff` and `remote` for each closest candidate.
2. `--format=json` returns an object under `closest_binaries` without losing the
   structured lists described above.
3. Default text output reuses compact package-list formatting. Refactor that
   formatter so callers can prepare an already-serialized package list without
   a fake remote wrapper. Compact diff values join lists with `, `, print
   `expected` in red and `existing` in green, and retain the explanation.
4. Existing `conan list` compact output and graph-related commands must remain
   backward-compatible.

The hidden verifier overlays trusted upstream tests and runs all new distance,
dependency, CLI, JSON, text-format, missing-selection, and regression cases out
of process. The reference implementation must pass the identical verifier and
the unmodified snapshot must fail. Network access is unnecessary; tests use
local fake remotes. Verifier budget: 180 seconds.

