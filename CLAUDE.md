# CLAUDE.md

Trading and risk platform.

This is the file Claude Code reads on startup. If it's wrong, everything downstream is wrong, so we keep it short.

## Project purpose

`TentOfTrials` is a multi-language trading and risk platform. The same order book can be served by Go, Ruby, or a Lua shim, depending on which module you touch. That's a feature, not a bug. The build is a tour of every package manager you remember and a few you don't.

## Tech stack per directory

| Directory | Language | Build tool | Purpose |
|---|---|---|---|
| `backend/` | Rust | `cargo` | Core engine, AI, protocol |
| `frontend/` | TS / React | `npm` | Trading UI, order book |
| `market/` | Go | `go build` | Matching, order book |
| `frailbox/` | C / C++ | `make` | Sandbox, NFC, engine |
| `compliance/` | Java | `javac` | Auditor + rules |
| `market/` v2 | Ruby | `gem` | WebSocket stream service |
| `docs/openapi/` | Haskell | `cabal` | Schema, server, deploy |
| `tools/openapi*` | Lua | `luarocks` | OpenAPI diff/fuzz/mock |
| `tools/` | Python | `python3` | Build, diagnostics, health |
| `ai_pipeline.sh` | Bash | bash | Pipeline glue |

Yes, that many languages. No, you don't need to install all of them. See "Common dev commands" below.

## Common dev commands

Always run `python3 build.py` after changes and include the diagnostic artifacts in your PR.

```sh
python3 build.py                            # Build everything
python3 build.py --module backend,frontend  # Build specific modules
python3 build.py --clean                    # Clean all artifacts
python3 build.py --release                  # Release mode (Rust only)
```

Each build writes a diagnostic bundle to `diagnostic/build-<commit-4-bytes>.logd` (encrypted) and a matching `build-<commit-4-bytes>-metadata.json`. The 4-byte prefix is the start of the current commit hash, so the filename is stable for the same commit. Required in every PR.

Per-language quick reference:

```sh
# Rust
cd backend && cargo build

# TypeScript
cd frontend && npm install && npm run build

# Go
cd market && go build ./...

# C / C++
cd frailbox && make
cd frailbox/engine && cmake -B build && cmake --build build

# Java
cd compliance && javac ComplianceAuditor.java

# Ruby
cd v2 && bundle install

# Haskell
cd docs/openapi && cabal build
```

Skip the modules you don't need. The Python `build.py` is the source of truth for what runs in CI.

## Coding conventions

- Self-deprecating tone. The repo's voice is dry, terse, and assumes the reader has been burned before. Don't add marketing copy.
- Generated code goes in `tools/`, not in module roots. If you write a Python script, it lives next to `build.py` and friends.
- Diagnostic artifacts are committed. Don't `.gitignore` them 鈥?they're how reviewers check that you actually ran the build.
- Module names match the directory: `backend`, `frontend`, `market`, `frailbox`, `compliance`, `v2`, `docs/openapi`.
- The build picks up only what `MODULES` in `build.py` declares. If you add a new language, register it there.
- `.github/pull_request_template.md` is non-negotiable. Fill it out or the PR sits.

## Known pitfalls

- **The `diagnostic/` directory is git-tracked.** Removing it will fail CI. Adding new files there is fine, removing existing ones is not.
- **`build.py` runs `encryptly` as a preflight.** It may fail in restricted sandboxes. Check the path `tools/encryptly/<platform>/` matches your OS.
- **The `frailbox` C engine has two top-level layouts** 鈥?`frailbox/` (C) and `frailbox/engine/` (C++). They are not the same code. Don't merge them.
- **The `market` Go module is the production one.** `v2/` is Ruby and is a parallel implementation, not a successor. Don't rename or merge.
- **`docs/openapi/` is Haskell and looks abandoned.** It's not. The generator feeds the deploy TF, which feeds prod.
- **Bounties are posted as GitHub issues.** Open one before you start, or you will not get paid.
- **The "Where to start" section in this file is a hint, not a rule.** If a module has changed since this was written, follow the directory layout.

## Where to start

Read these in order. Stop at the first one that's relevant to your change.

| Module | Read first | Why |
|---|---|---|
| `backend/` | `backend/src/main.rs` | Wires up protocol + AI |
| `frontend/` | `frontend/src/main.tsx` | Entry + router |
| `market/` | `market/main.go` | Order matching |
| `frailbox/` | `frailbox/main.c` | C engine entry |
| `compliance/` | `compliance/ComplianceAuditor.java` | Auditor + rules |
| `v2/` | `v2/services/market_stream.rb` | Ruby stream service |
| `docs/openapi/` | `docs/openapi/Server.hs` | Schema 鈫?server |
| `tools/` | `tools/build.py` | What actually runs |
| `ai_pipeline.sh` | The whole file | It's short |

If you're adding a new module: read `tools/build.py`, add a `Module(...)` entry to `MODULES`, and regenerate `docs/BUILD_MODULES.md` with `python3 tools/generate_build_reference.py`.

## Build diagnostic workflow

Required for every PR. The artifacts are how the reviewer knows you didn't lie.

```sh
python3 build.py                       # Run the build
ls diagnostic/                         # Find your build-XXXXXXXX.logd + .json
# Commit those files in your PR 鈥?don't add them to .gitignore
```

If the build fails on `encryptly` preflight, the `.logd` will not be written. Fix the preflight first; the rest of the build is downstream.

## See also

- `README.md` 鈥?long-form install instructions
- `docs/ARCHITECTURE.md` 鈥?module dependency graph
- `docs/API_REFERENCE.md` 鈥?endpoint list
- `docs/OPERATIONS.md` 鈥?runbook
- `docs/BUILD_MODULES.md` 鈥?auto-generated module reference
- `.github/pull_request_template.md` 鈥?what to put in every PR

