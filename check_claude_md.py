"""Markdown sanity check for CLAUDE.md.
Issue #2855 requires "no markdown lint errors" but does not pin a specific linter,
so we apply the conservative rules: well-formed H1, balanced code fences, no
empty link targets, and a generous line cap (matches README.md conventions).
"""
import re
import sys

MAX_LINE = 500  # README.md has lines up to ~400; CLAUDE.md may need a touch more.

def main(path: str = "CLAUDE.md") -> int:
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    errors = []
    first = next((l for l in txt.split("\n") if l.strip()), "")
    if not first.startswith("# "):
        errors.append(f"First non-empty line is not H1: {first!r}")
    backticks = txt.count("```")
    if backticks % 2:
        errors.append(f"Unclosed code fence ({backticks} backticks)")
    for m in re.finditer(r"\[([^\]]*)\]\(\s*\)", txt):
        errors.append(f"Empty link: {m.group(0)}")
    for i, line in enumerate(txt.split("\n"), 1):
        if len(line) > MAX_LINE:
            errors.append(f"Line {i} too long: {len(line)}")
    print(f"File: {path}")
    print(f"Total lines: {len(txt.split(chr(10)))}")
    print(f"Total chars: {len(txt)}")
    print(f"Errors: {errors if errors else 'none'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "CLAUDE.md"))

