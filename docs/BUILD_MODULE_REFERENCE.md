# Build Module Reference

Auto-generated reference for all modules in TentOfTrials.

## Overview

TentOfTrials is a multi-language trading and risk platform with **11 modules** spanning **8 programming languages**. Each module has independent build, clean, and diagnostic pipelines.

## Modules

### 1. backend (Rust)

| Field | Value |
|---|---|
| **Language** | Rust |
| **Directory** | `backend/` |
| **Build Command** | `cargo build` |
| **Clean Command** | `cargo clean` |
| **Build Output** | `backend/target/` |
| **Environment** | `CARGO_TERM_COLOR=always` |
| **Toolchain** | Rustup + Cargo |

**Description**: Core backend service for the trading platform.

---

### 2. frontend (TypeScript)

| Field | Value |
|---|---|
| **Language** | TypeScript |
| **Directory** | `frontend/` |
| **Build Command** | `npm run build` |
| **Clean Command** | `rm -rf node_modules dist` |
| **Build Output** | `frontend/dist/` |
| **Environment** | `NODE_ENV=production` |
| **Toolchain** | Node.js + npm |

**Description**: Frontend web application.

---

### 3. market (Go)

| Field | Value |
|---|---|
| **Language** | Go |
| **Directory** | `market/` |
| **Build Command** | `go build -o market .` |
| **Clean Command** | `rm -f market` |
| **Build Output** | `market/market` |
| **Environment** | — |
| **Toolchain** | Go |

**Description**: Market trading engine written in Go.

---

### 4. frailbox (C)

| Field | Value |
|---|---|
| **Language** | C |
| **Directory** | `frailbox/` |
| **Build Command** | `make` |
| **Clean Command** | `make distclean` |
| **Build Output** | `frailbox/frailbox` |
| **Environment** | — |
| **Toolchain** | GCC + Make |

**Description**: Low-level framework/container system.

---

### 5. engine (C++)

| Field | Value |
|---|---|
| **Language** | C++ |
| **Directory** | `frailbox/engine/` |
| **Build Command** | `cmake --build build` |
| **Clean Command** | `rm -rf build` |
| **Build Output** | `frailbox/engine/build/trial-engine` |
| **Environment** | — |
| **Toolchain** | CMake + GCC/G++ |

**Description**: Trial engine component within the frailbox system.

---

### 6. compliance (Java)

| Field | Value |
|---|---|
| **Language** | Java |
| **Directory** | `compliance/` |
| **Build Command** | `javac -d build ComplianceAuditor.java` |
| **Clean Command** | `rm -rf build` |
| **Build Output** | `compliance/build/` |
| **Environment** | — |
| **Toolchain** | OpenJDK 21 |

**Description**: Compliance auditing system.

---

### 7. v2-market-stream (Ruby)

| Field | Value |
|---|---|
| **Language** | Ruby |
| **Directory** | `v2/services/` |
| **Build Command** | `ruby -c market_stream.rb` |
| **Clean Command** | `echo "Ruby has no build artifacts to clean"` |
| **Build Output** | N/A (interpreted) |
| **Environment** | — |
| **Toolchain** | Ruby + EventMachine |

**Description**: Redis Pub/Sub market stream service (v2).

---

### 8. nfc-scanner (Lua)

| Field | Value |
|---|---|
| **Language** | Lua |
| **Directory** | `frailbox/nfc/` |
| **Build Command** | `luac -p scanner.lua` |
| **Clean Command** | `echo "Lua has no build artifacts to clean"` |
| **Build Output** | N/A (interpreted) |
| **Environment** | — |
| **Toolchain** | Lua 5.4 + Luarocks |

**Description**: NFC scanning component within frailbox.

---

### 9. openapi-haskell (Haskell)

| Field | Value |
|---|---|
| **Language** | Haskell |
| **Directory** | `docs/openapi/` |
| **Build Command** | `ghc -fno-code Types.hs Server.hs Validate.hs Generate.hs` |
| **Clean Command** | `rm -f *.hi *.o *.hie` |
| **Build Output** | N/A (compiled to object files) |
| **Environment** | — |
| **Toolchain** | GHC + Cabal |

**Description**: OpenAPI specification types and server in Haskell.

---

### 10. openapi-tools (Lua)

| Field | Value |
|---|---|
| **Language** | Lua |
| **Directory** | `tools/` |
| **Build Command** | `luac -p openapi_diff.lua openapi_mock.lua openapi_pact.lua` |
| **Clean Command** | `echo "Nothing to clean"` |
| **Build Output** | N/A (interpreted) |
| **Environment** | — |
| **Toolchain** | Lua 5.4 + Luarocks |

**Description**: OpenAPI utility tools (diff, mock, pact testing).

---

## Language Distribution

| Language | Modules |
|---|---|
| **Rust** | 1 (backend) |
| **TypeScript** | 1 (frontend) |
| **Go** | 1 (market) |
| **C** | 1 (frailbox) |
| **C++** | 1 (engine) |
| **Java** | 1 (compliance) |
| **Ruby** | 1 (v2-market-stream) |
| **Lua** | 2 (nfc-scanner, openapi-tools) |
| **Haskell** | 1 (openapi-haskell) |

---

## Build System

All modules are orchestrated by `build.py`:

```bash
# Build all modules
python3 build.py

# Build specific modules
python3 build.py --module backend,frontend

# Clean all artifacts
python3 build.py --clean

# Release mode (Rust optimization)
python3 build.py --release
```

Each build writes a diagnostic bundle to `diagnostic/` directory:
- Encrypted log: `build-<commit-4bytes>.logd`
- Metadata: `build-<commit-4bytes>-metadata.json`

---

## Encryptly Integration

The build system integrates with **Encryptly** for secure diagnostic bundling:

| Platform | Binary Path |
|---|---|
| Linux x64 | `tools/encryptly/linux-x64/encryptly` |
| Linux ARM64 | `tools/encryptly/linux-arm64/encryptly` |
| macOS ARM64 | `tools/encryptly/macos-arm64/encryptly` |
| macOS x64 | `tools/encryptly/macos-x64/encryptly` |
| Windows x64 | `tools/encryptly/windows-x64/encryptly.exe` |
| Windows ARM64 | `tools/encryptly/windows-arm64/encryptly.exe` |

---

*Generated from `build.py` MODULES list.*
