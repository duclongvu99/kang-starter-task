# Task N — Generalize system tools into platform requirements

Evolve Conan profiles and dependency resolution so both regular requirements
and tool requirements may be supplied by the platform rather than the Conan
cache. This is a cross-cutting change spanning profile parsing/composition,
graph resolution, binary status, package IDs, generator visibility, lockfiles,
metadata, API serialization, and user-facing output.

This task is derived from the public Conan feature implemented upstream in PR
14871. Do not search for, fetch, or copy the upstream patch; implement from this
specification and the local codebase. Do not edit files below `conans/test/`.

## Profile model

1. Add `[platform_requires]` for host-context regular requirements and
   `[platform_tool_requires]` for build-context tool requirements.
2. Deprecate `[system_tools]` as an accepted alias of
   `[platform_tool_requires]`. Preserve compatibility but consistently call the
   resolved status `Platform`, never `System tool`.
3. Parse entries as recipe references, preserve optional revisions, and compose
   included/overlaid profiles deterministically. Duplicate/composed sections
   follow existing profile list semantics.
4. Profile dumps, copies, serialization, package-setting updates, and public
   accessors must retain both platform lists. Add the corresponding properties
   while keeping the deprecated system-tools access path compatible.

## Graph resolution

1. Before normal cache/remote resolution, match a requirement by recipe name
   against the appropriate platform list for its context and kind.
2. Exact versions match exact versions. A required version range matches when
   the platform version is inside the range and then resolves the graph node to
   that exact platform version. Respect prerelease-resolution rules.
3. When both sides specify revisions, they must agree. A platform revision may
   resolve an otherwise revision-less requirement. Non-matches fall through to
   normal resolution; they are not silently replaced.
4. Host `[platform_requires]` must not satisfy a tool requirement, and
   `[platform_tool_requires]` must not satisfy an ordinary host requirement.
5. Platform nodes have recipe and binary status `Platform`, require no download,
   build, metadata folder, or generated dependency files, but remain visible to
   consumers with the resolved reference.

## Cross-cutting behavior

- Text/JSON graph output and API model loading recognize the new status.
- Dependency iteration and traits treat platform dependencies like the former
  system-tool nodes where appropriate.
- CMakeDeps/PkgConfig-style generators do not emit files for platform nodes.
- Lockfiles record resolved platform versions and enforce them on replay.
- Package-ID modes remain stable; explicit platform revisions participate where
  the selected package-ID mode requires recipe revisions.
- Metadata collection skips platform-provided nodes.

The hidden verifier overlays the trusted upstream tests and exercises exact and
range matches, non-matches, revision agreement, consumer iteration, host/build
separation, profile composition, locks, generators, package-ID modes,
serialization, metadata, and legacy `[system_tools]` compatibility. The upstream
reference must pass the identical verifier; the unmodified snapshot and partial
renames must fail. Network access is unnecessary. Verifier budget: 180 seconds.

