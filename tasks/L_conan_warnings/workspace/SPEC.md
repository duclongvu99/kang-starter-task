# Task L — Add `core:warnings_as_errors`

Implement a repository-wide Conan feature: the built-in boolean configuration
`core:warnings_as_errors` makes actionable warnings and programmatic error
reports fail the current command, while diagnostics that merely report an
exception already being handled must remain printable and must not replace or
recursively mask that exception.

This task is derived from the public Conan feature request implemented upstream
in PR 15149. You are working from its real pre-change commit. Do not search for,
fetch, or copy the upstream patch; implement from this specification and the
local codebase. Do not edit files below `conans/test/`.

## Required behavior

1. Register `core:warnings_as_errors` in Conan's built-in configuration list.
   It defaults to `False` and must be read as a strict boolean from the loaded
   global configuration whenever a `ConanApp` is constructed. Existing
   `core:skip_warnings` initialization must continue to work.
2. `ConanOutput` must expose a class-level configuration hook for this mode.
   With the mode disabled, warning and error output is backward-compatible.
3. With the mode enabled, `warning(message, warn_tag=...)` becomes a
   `ConanException` at any output level that admits errors, even if ordinary
   warnings are hidden by `-verror`. The exception message includes the warning
   tag as `"tag: message"` when a tag exists.
4. Warning suppression happens before escalation. A tag listed in
   `core:skip_warnings` suppresses that tagged warning. The special tag name
   `"unknown"` suppresses untagged warnings. Suppressed warnings neither print
   nor raise.
5. Extend `ConanOutput.error` so call sites can distinguish an actionable error
   from a diagnostic associated with an exception that already exists. In
   warnings-as-errors mode, actionable errors raise `ConanException`; exception
   diagnostics still print `ERROR:` and return normally.
6. Audit all production call sites of `.error(...)`. Mark exception-reporting
   sites so they preserve the original control flow. This includes CLI exception
   rendering, custom-command load failures, integrity reports, deploy/unzip and
   generator failures, migrations, remote download/upload/authentication
   cleanup, graph-lock/install diagnostics, and similar paths. Do not solve the
   task by globally exempting every error.
7. Network retry notices currently emitted as errors by the downloader and
   uploader become tagged warnings (`network`) so the new policy treats them
   consistently.
8. A missing `--build` pattern is an actionable error report; expose the
   existing unused-pattern information through `BuildMode.report_matches()`.
9. Normal command exception handling must still return the established Conan
   exit codes and render the original exception once. Warnings-as-errors must
   not cause a second exception while printing it.

## Acceptance contract

The hidden verifier installs trusted upstream feature tests over a throwaway
copy, runs them out of process, and also runs focused pre-existing regression
tests for affected exception paths. It checks warning tags, untagged warnings,
verbosity `-vwarning`/`-verror`, disabled mode, exception diagnostics, retry
classification, and CLI exit behavior. The reference upstream implementation
must pass the same verifier and the unmodified snapshot must fail.

Use only repository code and the installed Python dependencies. Network access
is unnecessary. The total verifier budget is 180 seconds.

