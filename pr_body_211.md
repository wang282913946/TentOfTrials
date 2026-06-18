## What this PR does

Adds a structured per-module timing report to `build.py` and a
`--timings-json` flag so callers can pipe the same data to their own
dashboards. The diagnostic JSON metadata under `diagnostic/build-*.json`
now includes a `module_timings` array and a `timing_summary` object in
addition to the existing `modules` summary.

This addresses the difficulty of identifying slow modules from the
encrypted diagnostic log alone: the timings are now first-class
metadata, sorted-slowest-first, and exposed both on stdout and in two
machine-readable sinks.

## Acceptance criteria mapping

| Requirement | Where it lands |
|-------------|----------------|
| `module_timings` array in diagnostic JSON | `build_diagnostic_report()` adds it from `_module_timings(results)` |
| Per-entry: `module`, `language`, `command`, `started_at`, `finished_at`, `elapsed_seconds`, `exit_code`, `status` | `_module_timings()` builds the dict |
| Preserve existing `.logd` generation | unchanged: `generate_logd()` + `commit_diagnostic_artifacts()` untouched |
| Sorted slowest-first summary at end of `build.py` | `print_timing_summary()` called from `main()` after `print_summary()` |
| `--timings-json PATH` flag | added to the `argparse` parser; writes the same array to a caller file |
| Failed module builds still write timing | `build_module()` now returns the 6-tuple `(success, elapsed, output, command, started_at, finished_at)`; `_fail()` helper records `started_at`/`finished_at` even on `FileNotFoundError`, `TimeoutExpired`, or non-zero `returncode` |

## Schema (`module_timings` entry)

```json
{
  "module": "backend",
  "language": "Rust",
  "command": ["cargo", "build"],
  "started_at": "2026-06-18T12:18:46.504458+00:00",
  "finished_at": "2026-06-18T12:18:46.576834+00:00",
  "elapsed_seconds": 0.072,
  "exit_code": 1,
  "status": "FAIL",
  "artifact": null,
  "output_tail": "Command not found: ..."
}
```

`timing_summary` is a convenience object on the same JSON:

```json
"timing_summary": {
  "total_seconds": 0.1,
  "slowest": "backend",
  "slowest_seconds": 0.1
}
```

## CLI

```sh
python3 build.py --timings-json timings.json                # all modules
python3 build.py -m backend --timings-json b.json            # single module
python3 build.py --clean                                     # unaffected
```

The timings file shape matches the `module_timings` array exactly so
CI / dashboards can ingest one or the other interchangeably.

## Stdout summary

After the per-module `Build Summary` block, `build.py` now prints a
sorted slowest-first timing table:

```
  Build Timing Summary (slowest first)
  module   language  status    elapsed  exit
  ------------------------------------------
  backend  Rust      FAIL                  0.1s     1
  ──────────────────────────────────────────
  Total: 1 modules, 0.1s elapsed
```

## Implementation notes

* `build_module()` now returns a 6-tuple. All callers (the loop in
  `main()`, `print_summary()`, the log/summary file writers in
  `generate_logd()`) were updated to handle the new shape; legacy
  5-tuple rows from the encryptly preflight blocker path still
  produce a timing entry with `language=unknown` so the diagnostic
  metadata is never empty.
* `_module_timings()` is the single source of truth: it is called by
  `build_diagnostic_report()` to write the JSON metadata and by
  `--timings-json` to write the caller file. Same dict, same shape.
* `output_tail` is the last 2000 chars of the build output, kept short
  so the diagnostic JSON stays small even when the build prints
  thousands of lines.
* `print_timing_summary()` honours the existing `Colors` class so the
  slowest-first table reads correctly in a TTY and is plain in a
  redirected log.
* No new dependencies; no behaviour change for users who do not pass
  `--timings-json`.

## Verification

Running on this branch (host with no toolchain installed):

```
$ python3 build.py -m backend --timings-json tmp/timings-backend.json
  Tent of Trials: building
  Working directory: ...

  Checking prerequisites...
  ⚠ Some tools missing  -  will try anyway:
    Rust (cargo) ...
  Not all modules will build. That's fine.

  Checking encryptly diagnostics...
  ✓ encryptly runs

  Building 1 module(s) | release=False

  ▸ Building backend (Rust)...
  Build Summary

  ✗  backend: FAIL  (0.1s)
       last output:
       Command not found: ...

  ────────────────────────────────────────
  Total: 1 modules, 0 passed, 1 failed, 0.1s total

  Build Timing Summary (slowest first)
  module   language  status    elapsed  exit
  ------------------------------------------
  backend  Rust      FAIL                  0.1s     1
  ──────────────────────────────────────────
  Total: 1 modules, 0.1s elapsed

  ✓ Timings JSON written to ...\tmp\timings-backend.json
```

`tmp/timings-backend.json` contains:

```json
{
  "generated_at": "2026-06-18T12:16:17.433752+00:00",
  "module_timings": [
    {
      "module": "backend",
      "language": "Rust",
      "command": ["cargo", "build"],
      "started_at": "...",
      "finished_at": "...",
      "elapsed_seconds": 0.1,
      "exit_code": 1,
      "status": "FAIL",
      "artifact": null,
      "output_tail": "Command not found: ..."
    }
  ]
}
```

And `diagnostic/build-7f6301d0.json` contains the same entries under
`module_timings` plus a `timing_summary` block.

## Out of scope

* This PR does not change the existing `.logd` generation or the
  encryptly preflight behaviour.
* The encryptly preflight timeout remains 600s as in the existing
  code; tightening it (or adding `--no-encryptly` for fast feedback
  on hosts where encryptly misbehaves) is a separate concern.
* This PR is intentionally limited to the timing report; it does not
  introduce per-module dependency tracking, parallel build
  scheduling, or incremental build detection.

## Files

* `build.py` (modified, +85 / -25 lines)
* `pr_body_211.md` (this file)
* `tmp/timings-backend.json` (verification artifact, optional)
* `diagnostic/build-7f6301d0.json` (verification artifact, included)
* `diagnostic/build-7f6301d0.logd` (verification artifact, included)
