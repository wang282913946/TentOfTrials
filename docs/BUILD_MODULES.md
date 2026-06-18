# Build Module Reference

This document describes every entry in the `MODULES` list defined in
`build.py` and the rules `tools/validate_modules.py` uses to check them
before any build runs. It is the human-readable companion to the
validator and is updated whenever a new module is added or an existing
one is renamed.

## 1. What the validator checks

For every module in `MODULES` the validator (`tools/validate_modules.py`)
performs the following checks. The exit code is `0` only if **no ERRORs**
are reported; pass `--strict` to also fail on `WARNING`s.

| Check              | Severity on failure | What it verifies                                              |
|--------------------|---------------------|---------------------------------------------------------------|
| `directory_exists` | ERROR               | The source directory resolves under `ROOT` and is a directory |
| `build_cmd_runnable` | WARNING           | The head of `build_cmd` is on `PATH` (or is a shell builtin)  |
| `clean_cmd_runnable` | WARNING           | The head of `clean_cmd` is on `PATH` (or is a shell builtin)  |
| `build_dir_ok`     | ERROR               | If `build_dir` is set, the path either exists or is creatable |
| `language_set`     | ERROR               | The `language` field is a non-empty string                    |
| `name_unique`      | ERROR               | No other module shares the same `name`                        |
| `dir_unique`       | ERROR               | No other module shares the same source directory              |

Toolchain warnings are normal on a developer workstation that only
installs a subset of the toolchain. The validator never blocks the
build on these.

## 2. Module table

The following table mirrors `MODULES` in `build.py` as of this
revision. Re-run `python3 tools/validate_modules.py` after editing the
list to regenerate the same view from source.

| Name              | Language    | Source dir          | Build command                                            | Clean command                          | Output dir                              |
|-------------------|-------------|---------------------|----------------------------------------------------------|----------------------------------------|-----------------------------------------|
| `backend`         | Rust        | `backend`           | `cargo build`                                            | `cargo clean`                          | `backend/target`                        |
| `frontend`        | TypeScript  | `frontend`          | `npm run build`                                          | `rm -rf node_modules dist`             | `frontend/dist`                         |
| `market`          | Go          | `market`            | `go build -o market .`                                   | `rm -f market`                         | `market/market`                         |
| `frailbox`        | C           | `frailbox`          | `make`                                                   | `make distclean`                       | `frailbox/frailbox`                     |
| `engine`          | C++         | `frailbox/engine`   | `cmake --build build`                                    | `rm -rf build`                         | `frailbox/engine/build/trial-engine`    |
| `compliance`      | Java        | `compliance`        | `javac -d build ComplianceAuditor.java`                  | `rm -rf build`                         | `compliance/build`                      |
| `v2-market-stream`| Ruby        | `v2/services`       | `ruby -c market_stream.rb`                               | `echo Ruby has no build artifacts...`  | _(none)_                                |
| `nfc-scanner`     | Lua         | `frailbox/nfc`      | `luac -p scanner.lua`                                    | `echo Lua has no build artifacts...`   | _(none)_                                |
| `openapi-haskell` | Haskell     | `docs/openapi`      | `ghc -fno-code Types.hs Server.hs Validate.hs Generate.hs` | `rm -f *.hi *.o *.hie`               | _(none)_                                |
| `openapi-tools`   | Lua         | `tools`             | `luac -p openapi_diff.lua openapi_mock.lua openapi_pact.lua` | `echo Nothing to clean`           | _(none)_                                |

## 3. How to add a new module

1. Add a `Module(...)` entry to the `MODULES` list in `build.py`. Use
   `ROOT / "..."` for both `dir` and `build_dir` so the path is
   relative to the repository root. The validator parses this with
   `ast` and only accepts a single `ROOT` prefix - it does not
   evaluate arbitrary expressions, so the same compile-time safety
   applies as for the rest of the file.
2. Run `python3 tools/validate_modules.py` to confirm the entry
   parses and the directory exists.
3. Add a row to the table above (or run the validator and paste the
   output) and commit both the code and the doc change in the same PR.
4. If the module is brand-new, also add an entry to `README.md`
   "Build" section so users see the new build command.

## 4. How to run the validator

```sh
# Validate every module.
python3 tools/validate_modules.py

# Validate a single module.
python3 tools/validate_modules.py -m backend

# Create missing source / build directories before reporting.
python3 tools/validate_modules.py --fix

# JSON output for CI / dashboards.
python3 tools/validate_modules.py --json

# Treat warnings as failures (use in CI).
python3 tools/validate_modules.py --strict
```

The validator is intentionally standalone: it parses `build.py` with
`ast` rather than importing it, so it can run on a host where the full
build toolchain is not installed. This is also why it does not invoke
`build.py` itself - that would have the side effect of writing
diagnostic artifacts under `diagnostic/`.

## 5. Why a separate validator

`build.py` is intentionally permissive: it tries to build every
selected module and only fails per-module, never at the top level.
The downside is that a typo in a `Module(...)` entry - wrong directory,
missing toolchain, duplicate name - only surfaces when that module is
actually built, and the failure is buried inside the build log.

`tools/validate_modules.py` front-loads those checks so the issue
appears before `cargo` / `npm` / `go` even start. The script is
idempotent, runs in under a second, and is safe to wire into CI
without any other setup.
