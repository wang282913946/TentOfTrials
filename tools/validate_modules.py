#!/usr/bin/env python3
"""
Validate module definitions in build.py's MODULES list (bounty #225).

This tool reads the `MODULES` list exported by `build.py` and checks each
entry for common issues that would surface only at build time:

  * directory_exists  - module source directory is present on disk
  * build_cmd_runnable- the leading token in `build_cmd` is on PATH
  * clean_cmd_runnable- the leading token in `clean_cmd` is on PATH
                        (built-in shell commands such as `rm`/`echo` are
                        considered safe and skipped)
  * build_dir_ok      - if `build_dir` is set, the path either exists or
                        is creatable under ROOT
  * language_set      - the `language` field is a non-empty string
  * name_unique       - no other module in MODULES shares the same `name`
  * dir_unique        - no other module in MODULES shares the same `dir`

The script is intentionally standalone - it does not import `build.py`
(because that executes the build logic and tries to write a diagnostic
artifact). Instead, it parses the source text of `build.py` with the
`ast` module and extracts the module-defining `Module(...)` calls from
the `MODULES = [ ... ]` assignment. This means it works on any host
without requiring the build toolchain to be installed.

Usage:
    python3 tools/validate_modules.py               # validate all modules
    python3 tools/validate_modules.py -m backend    # validate one module
    python3 tools/validate_modules.py --json        # machine-readable
    python3 tools/validate_modules.py --strict      # exit 1 on warnings
    python3 tools/validate_modules.py --fix         # create missing dirs
"""

import argparse
import ast
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
BUILD_PY = ROOT / "build.py"

# Commands that are shell builtins or simple file ops and do not need
# to be on PATH. Everything else must be discoverable via shutil.which.
SHELL_BUILTINS = {
    "echo", "rm", "rmdir", "cat", "ls", "mkdir", "touch", "cp", "mv",
    "pwd", "cd", "true", "false", "test",
}

REQUIRED_KEYWORDS = (
    "name", "language", "dir", "build_cmd", "clean_cmd", "build_dir", "env",
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ModuleDef:
    name: str
    language: str
    dir: str
    build_cmd: List[str]
    clean_cmd: List[str]
    build_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    line: int = 0  # source line for nicer error messages


@dataclass
class Issue:
    severity: str  # "ERROR" | "WARNING"
    message: str


@dataclass
class ModuleReport:
    module: ModuleDef
    issues: List[Issue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.severity == "ERROR" for i in self.issues)

    @property
    def status(self) -> str:
        if not self.passed:
            return "ERROR"
        if any(i.severity == "WARNING" for i in self.issues):
            return "WARNING"
        return "OK"


# ---------------------------------------------------------------------------
# Parsing: pull MODULES out of build.py via the AST
# ---------------------------------------------------------------------------

def _literal(node: ast.AST):
    """Recursively evaluate a literal AST node (str/int/float/bool/None/list/tuple/dict)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(x) for x in node.elts]
    if isinstance(node, ast.Dict):
        return {_literal(k): _literal(v) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _literal(node.operand)
        if isinstance(v, (int, float)):
            return -v
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        # build.py writes `ROOT / "x"` and `ROOT / "x" / "y" / "z"`. Walk
        # down the left side to collect every constant and join them,
        # requiring the leftmost node to be `Name("ROOT")` so we never
        # accept arithmetic on arbitrary expressions.
        parts: list[str] = []
        current = node
        while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
            if isinstance(current.right, ast.Constant) and isinstance(current.right.value, str):
                parts.append(current.right.value)
            current = current.left
        if isinstance(current, ast.Name) and current.id == "ROOT" and parts:
            return "/".join(reversed(parts))
    raise ValueError(f"unsupported literal node: {type(node).__name__}")


def _call_keyword(call: ast.Call, key: str) -> Optional[ast.AST]:
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def parse_modules_from_build_py(path: Path = BUILD_PY) -> List[ModuleDef]:
    """Extract the MODULES list from build.py without importing it."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    modules_node: Optional[ast.AST] = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MODULES":
                    modules_node = node.value
                    break
        if modules_node is not None:
            break

    if modules_node is None or not isinstance(modules_node, ast.List):
        raise SystemExit("could not locate `MODULES = [...]` in build.py")

    out: List[ModuleDef] = []
    for entry in modules_node.elts:
        if not isinstance(entry, ast.Call):
            continue
        # Verify the function being called is named `Module` (the dataclass).
        if isinstance(entry.func, ast.Name) and entry.func.id != "Module":
            continue

        def kw(key: str, default=None):
            node = _call_keyword(entry, key)
            if node is None:
                return default
            return _literal(node)

        name = kw("name")
        language = kw("language")
        dir_value = kw("dir")
        build_cmd = kw("build_cmd", default=[])
        clean_cmd = kw("clean_cmd", default=[])
        build_dir = kw("build_dir")
        env = kw("env")

        if not isinstance(name, str) or not name:
            raise SystemExit("MODULE entry missing required `name=<str>`")
        if not isinstance(language, str) or not language:
            raise SystemExit(f"MODULE {name!r} missing `language`")
        if not isinstance(dir_value, str):
            raise SystemExit(f"MODULE {name!r} missing `dir=<str|Path>`")
        if not isinstance(build_cmd, list) or not all(isinstance(x, str) for x in build_cmd):
            raise SystemExit(f"MODULE {name!r} has invalid `build_cmd`")
        if not isinstance(clean_cmd, list) or not all(isinstance(x, str) for x in clean_cmd):
            raise SystemExit(f"MODULE {name!r} has invalid `clean_cmd`")
        if build_dir is not None and not isinstance(build_dir, str):
            raise SystemExit(f"MODULE {name!r} has invalid `build_dir`")
        if env is not None and not isinstance(env, dict):
            raise SystemExit(f"MODULE {name!r} has invalid `env`")

        if isinstance(entry.args, list) and entry.args:
            raise SystemExit("positional args in MODULE entries are not supported")

        out.append(ModuleDef(
            name=name,
            language=language,
            dir=dir_value,
            build_cmd=list(build_cmd),
            clean_cmd=list(clean_cmd),
            build_dir=build_dir,
            env=dict(env) if env else None,
            line=entry.lineno,
        ))

    if not out:
        raise SystemExit("no MODULE(...) entries found in MODULES list")
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _resolve_under_root(value: str) -> Path:
    """Treat `value` as either absolute or relative-to-ROOT."""
    p = Path(value)
    if p.is_absolute():
        return p
    return ROOT / p


def validate_module(module: ModuleDef, all_modules: List[ModuleDef]) -> ModuleReport:
    report = ModuleReport(module=module)

    # 1. directory_exists
    if not module.dir:
        report.issues.append(Issue("ERROR", "missing `dir`"))
    else:
        src = _resolve_under_root(module.dir)
        if not src.exists():
            report.issues.append(Issue("ERROR", f"source directory does not exist: {module.dir}"))
        elif not src.is_dir():
            report.issues.append(Issue("ERROR", f"`{module.dir}` is not a directory"))

    # 2. build_cmd_runnable
    if not module.build_cmd:
        report.issues.append(Issue("ERROR", "empty `build_cmd`"))
    else:
        head = module.build_cmd[0]
        if head in SHELL_BUILTINS or shutil.which(head) is not None:
            pass
        else:
            report.issues.append(Issue(
                "WARNING",
                f"build_cmd head `{head}` is not on PATH (module cannot be built here)",
            ))

    # 3. clean_cmd_runnable
    if not module.clean_cmd:
        report.issues.append(Issue("ERROR", "empty `clean_cmd`"))
    else:
        head = module.clean_cmd[0]
        if head in SHELL_BUILTINS or shutil.which(head) is not None:
            pass
        else:
            report.issues.append(Issue(
                "WARNING",
                f"clean_cmd head `{head}` is not on PATH",
            ))

    # 4. build_dir_ok
    if module.build_dir is None:
        pass
    else:
        bd = _resolve_under_root(module.build_dir)
        if bd.exists() and not bd.is_dir():
            report.issues.append(Issue("ERROR", f"build_dir `{module.build_dir}` is not a directory"))
        # Note: it is normal for build_dir to be absent before the first build.

    # 5. language_set
    if not module.language:
        report.issues.append(Issue("ERROR", "`language` is empty"))

    # 6. name_unique
    name_clash = [m.name for m in all_modules if m is not module and m.name == module.name]
    if name_clash:
        report.issues.append(Issue("ERROR", f"duplicate module name (also used by: {', '.join(name_clash)})"))

    # 7. dir_unique
    dir_clash = [m.name for m in all_modules if m is not module and m.dir == module.dir]
    if dir_clash:
        report.issues.append(Issue("ERROR", f"duplicate source dir `{module.dir}` (also used by: {', '.join(dir_clash)})"))

    return report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    GRAY = "\033[90m"


def _color(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{Colors.RESET}" if enabled else text


def print_human(reports: List[ModuleReport], use_color: bool) -> None:
    bar = "=" * 60
    print(bar)
    print(_color("Tent of Trials - Module Validation Report", Colors.BOLD, use_color))
    print(bar)
    for r in reports:
        m = r.module
        if r.status == "OK":
            head = _color(f"[OK]      {m.name} ({m.language}) @ line {m.line}", Colors.GREEN, use_color)
        elif r.status == "WARNING":
            head = _color(f"[WARNING] {m.name} ({m.language}) @ line {m.line}", Colors.YELLOW, use_color)
        else:
            head = _color(f"[ERROR]   {m.name} ({m.language}) @ line {m.line}", Colors.RED, use_color)
        print(head)
        print(f"    dir      = {m.dir}")
        print(f"    build    = {' '.join(m.build_cmd)}")
        print(f"    clean    = {' '.join(m.clean_cmd)}")
        if m.build_dir is not None:
            print(f"    out      = {m.build_dir}")
        for issue in r.issues:
            tag = _color(issue.severity, Colors.RED if issue.severity == "ERROR" else Colors.YELLOW, use_color)
            print(f"    {tag}: {issue.message}")
        print()

    # Summary
    total = len(reports)
    ok = sum(1 for r in reports if r.status == "OK")
    warn = sum(1 for r in reports if r.status == "WARNING")
    err = sum(1 for r in reports if r.status == "ERROR")
    print(bar)
    summary = f"Total {total} | OK {_color(str(ok), Colors.GREEN, use_color)} | " \
              f"WARNING {_color(str(warn), Colors.YELLOW, use_color)} | " \
              f"ERROR {_color(str(err), Colors.RED, use_color)}"
    print(summary)
    print(bar)


def print_json(reports: List[ModuleReport]) -> None:
    payload = {
        "total": len(reports),
        "ok": sum(1 for r in reports if r.status == "OK"),
        "warning": sum(1 for r in reports if r.status == "WARNING"),
        "error": sum(1 for r in reports if r.status == "ERROR"),
        "modules": [
            {
                "name": r.module.name,
                "language": r.module.language,
                "line": r.module.line,
                "status": r.status,
                "issues": [{"severity": i.severity, "message": i.message} for i in r.issues],
            }
            for r in reports
        ],
    }
    print(json.dumps(payload, indent=2))


def auto_fix(reports: List[ModuleReport]) -> List[str]:
    """Create any missing source / build directories. Returns a log of actions taken."""
    actions: List[str] = []
    for r in reports:
        m = r.module
        if not m.dir:
            continue
        src = _resolve_under_root(m.dir)
        if not src.exists():
            try:
                src.mkdir(parents=True, exist_ok=True)
                actions.append(f"created source dir: {m.dir}")
            except OSError as e:
                actions.append(f"FAILED to create source dir {m.dir}: {e}")
        if m.build_dir:
            bd = _resolve_under_root(m.build_dir)
            if not bd.exists():
                try:
                    bd.mkdir(parents=True, exist_ok=True)
                    actions.append(f"created build dir: {m.build_dir}")
                except OSError as e:
                    actions.append(f"FAILED to create build dir {m.build_dir}: {e}")
    return actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate module definitions in build.py (bounty #225)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("-m", "--module", help="Validate a single module by name")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.add_argument("--strict", action="store_true", help="Exit 1 on any WARNING (in addition to ERROR)")
    p.add_argument("--fix", action="store_true", help="Create any missing source / build directories")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    use_color = (not args.no_color) and sys.stdout.isatty() and (os.environ.get("NO_COLOR") is None)

    if not BUILD_PY.exists():
        print(f"error: build.py not found at {BUILD_PY}", file=sys.stderr)
        return 2

    modules = parse_modules_from_build_py()
    if args.module:
        modules = [m for m in modules if m.name == args.module]
        if not modules:
            print(f"error: module `{args.module}` not in MODULES", file=sys.stderr)
            return 2

    reports = [validate_module(m, modules) for m in modules]

    if args.fix:
        actions = auto_fix(reports)
        if actions:
            print("Auto-fix:")
            for a in actions:
                print(f"  {a}")
            print()
        # Re-validate so the report reflects the fix.
        reports = [validate_module(m, modules) for m in modules]

    if args.json:
        print_json(reports)
    else:
        print_human(reports, use_color)

    err_count = sum(1 for r in reports if r.status == "ERROR")
    warn_count = sum(1 for r in reports if r.status == "WARNING")
    if err_count:
        return 1
    if args.strict and warn_count:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
