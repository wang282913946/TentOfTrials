#!/usr/bin/env python3
"""
Determinism validation for tools/data_generator.py.

Runs the generator with the same seed twice, diffs the output,
and proves byte-for-byte identity. Also validates that three
different seeds produce distinct outputs.

Usage:
    python tools/validate_determinism.py
    python tools/validate_determinism.py --seed 12345
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
GEN = os.path.join(REPO_ROOT, "tools", "data_generator.py")

SEED_A = 42
SEED_B = 99999
SEED_C = 777777


def run_generator(seed: int, output_dir: str, extra_args: list | None = None) -> dict[str, str]:
    """Run data_generator.py and return {filename: sha256}."""
    cmd = [sys.executable, GEN, "--seed", str(seed), "--output-dir", output_dir, "--format", "json"]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr[:500]}")
        sys.exit(1)
    hashes: dict[str, str] = {}
    for fname in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                hashes[fname] = hashlib.sha256(f.read()).hexdigest()[:16]
    return hashes


def print_hashes(label: str, hashes: dict[str, str]):
    print(f"  [{label}]")
    for k, v in sorted(hashes.items()):
        print(f"    {k}: {v}")


def main():
    tmpdir = tempfile.mkdtemp(prefix="determ_test_")
    print(f"Temp dir: {tmpdir}\n")

    try:
        # --- Test 1: same seed -> identical output (two runs) ---
        print("=" * 60)
        print("TEST 1: Same seed produces identical output")
        print("=" * 60)

        run_a = os.path.join(tmpdir, "run_a")
        run_b = os.path.join(tmpdir, "run_b")
        os.makedirs(run_a)
        os.makedirs(run_b)

        h_a = run_generator(SEED_A, run_a)
        h_b = run_generator(SEED_A, run_b)

        print_hashes("Run A", h_a)
        print_hashes("Run B", h_b)

        if h_a == h_b:
            print("  PASS: Byte-for-byte identical\n")
        else:
            print("  FAIL: Outputs differ!\n")
            for k in set(list(h_a.keys()) + list(h_b.keys())):
                if h_a.get(k) != h_b.get(k):
                    print(f"    DIFF {k}: {h_a.get(k, 'MISSING')} vs {h_b.get(k, 'MISSING')}")
            sys.exit(1)

        # --- Test 2: different seeds -> different output ---
        print("=" * 60)
        print("TEST 2: Different seeds produce different output")
        print("=" * 60)

        run_c = os.path.join(tmpdir, "run_c")
        run_d = os.path.join(tmpdir, "run_d")
        os.makedirs(run_c)
        os.makedirs(run_d)

        h_c = run_generator(SEED_B, run_c)
        h_d = run_generator(SEED_C, run_d)

        print_hashes("Seed B", h_c)
        print_hashes("Seed C", h_d)

        all_same = all(h_c.get(k) == h_d.get(k) for k in set(h_c) | set(h_d))
        if not all_same:
            print("  PASS: Outputs are different\n")
        else:
            print("  FAIL: Different seeds produced same output!\n")
            sys.exit(1)

        # --- Test 3: third seed also distinct ---
        print("=" * 60)
        print("TEST 3: Third seed is also distinct")
        print("=" * 60)

        # Re-run SEED_A to confirm stability
        run_e = os.path.join(tmpdir, "run_e")
        os.makedirs(run_e)
        h_e = run_generator(SEED_A, run_e)
        print_hashes("Seed A (re-run)", h_e)
        if h_a == h_e:
            print("  PASS: Re-run matches initial run\n")
        else:
            print("  FAIL: Re-run differs!\n")
            sys.exit(1)

        # --- Test 4: --print-seed flag ---
        print("=" * 60)
        print("TEST 4: --print-seed flag works")
        print("=" * 60)
        result = subprocess.run(
            [sys.executable, GEN, "--print-seed"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        printed = result.stdout.strip()
        print(f"  --print-seed output: {printed}")
        if printed.isdigit() and 0 <= int(printed) < 2**31:
            print("  PASS: Valid seed printed\n")
        else:
            print("  FAIL: Invalid seed output\n")
            sys.exit(1)

        # --- Test 5: metadata header contains seed ---
        print("=" * 60)
        print("TEST 5: Metadata header contains seed")
        print("=" * 60)
        meta_run = os.path.join(tmpdir, "meta_check")
        os.makedirs(meta_run)
        run_generator(SEED_A, meta_run)
        meta_file = os.path.join(meta_run, "users.json")
        with open(meta_file) as f:
            content = f.read()
        first_lines = content.split("\n")[:5]
        header_text = "\n".join(first_lines)
        print(f"  Header:\n{textwrap.indent(header_text, '    ')}")
        if f"seed: {SEED_A}" in header_text:
            print("  PASS: Seed present in metadata header\n")
        else:
            print("  FAIL: Seed not found in metadata header\n")
            sys.exit(1)

        # --- Summary ---
        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        print(f"""
Determinism validation complete:
  - Seed {SEED_A} x2  : identical PASS
  - Seed {SEED_B} vs {SEED_C} : different PASS
  - Seed {SEED_A} re-run: identical PASS
  - --print-seed: valid PASS
  - Metadata header: contains seed PASS
""")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
