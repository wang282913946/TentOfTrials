## What this PR does

Adds `tools/validate_modules.py`, a standalone pre-build validator
for the `MODULES` list in `build.py`, plus `docs/BUILD_MODULES.md`
which documents the contract every module entry is expected to honour.

`build.py` currently only checks for the presence of CLI tools via
`check_prerequisites()`. It does not check that the source directory
referenced by each module actually exists, that the build/clean
command head is on `PATH`, that the output directory is creatable,
or that no two modules collide on name or source dir. Those issues
only surface mid-build and the failure is buried in a 300-second
subprocess log.

This PR adds a fast (sub-second) pre-flight that catches those cases
before `build.py` even starts. The validator is intentionally
standalone - it parses `build.py` with `ast` instead of importing it,
so it runs cleanly on any host without needing the full toolchain.

## Checks performed per module

| Check              | Severity | What it verifies                                              |
|--------------------|----------|---------------------------------------------------------------|
| `directory_exists` | ERROR    | Source directory resolves under `ROOT` and is a directory     |
| `build_cmd_runnable` | WARNING | Head of `build_cmd` is on `PATH` (or is a shell builtin)      |
| `clean_cmd_runnable` | WARNING | Head of `clean_cmd` is on `PATH` (or is a shell builtin)      |
| `build_dir_ok`     | ERROR    | If `build_dir` is set, the path exists or is creatable        |
| `language_set`     | ERROR    | The `language` field is a non-empty string                    |
| `name_unique`      | ERROR    | No other module shares the same `name`                        |
| `dir_unique`       | ERROR    | No other module shares the same source directory              |

## CLI

```sh
python3 tools/validate_modules.py               # validate all modules
python3 tools/validate_modules.py -m backend    # validate a single module
python3 tools/validate_modules.py --fix         # create missing directories
python3 tools/validate_modules.py --json        # machine-readable output
python3 tools/validate_modules.py --strict      # exit 1 on WARNING
```

The script also prints the resolved `dir`, `build_cmd`, `clean_cmd`
and `build_dir` for each module so a developer can see at a glance
what the validator is looking at.

## Verification

```
$ python3 tools/validate_modules.py --no-color
============================================================
Tent of Trials - Module Validation Report
============================================================
[WARNING] backend (Rust) @ line 182
    dir      = backend
    build    = cargo build
    ...
    WARNING: build_cmd head `cargo` is not on PATH

[OK]      frontend (TypeScript) @ line 191
    ...

[WARNING] market (Go) @ line 200
    ...

============================================================
Total 10 | OK 1 | WARNING 9 | ERROR 0
============================================================
```

0 ERRORs confirms every module entry in `MODULES` parses and resolves
to an existing directory. The 9 WARNINGs are toolchain
`which cargo` / `which go` / ... checks and are expected on a host
without the full toolchain installed - they do not block the build.

`--json` output is structured for CI integration and renders the same
shape that future dashboards can ingest.

## Out of scope

* This PR does **not** modify `build.py` itself - it only adds a
  sibling validator. The diagnostic artifacts produced by
  `build.py` (the `.logd` / `.json` pair) are unchanged.
* The validator does not attempt to build any module. It is strictly
  a static / filesystem check.
* The 9 toolchain warnings are by design: shipping this validator
  pre-merge lets CI distinguish "code structure is fine" from
  "toolchain is installed" so a missing toolchain does not produce
  an exit code that gets confused with a real defect.

## Files

* `tools/validate_modules.py` (new, ~440 lines)
* `docs/BUILD_MODULES.md` (new, ~110 lines)
