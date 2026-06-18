## Summary

Add `CLAUDE.md` at the repo root (issue #2855, $25 bounty). This is the file Claude Code reads on startup; before this PR, the assistant had to read 50K of README just to orient itself.

## Changes

- New `CLAUDE.md` (126 lines, well under the 500-line cap):
  - Project purpose
  - Tech stack per directory (10 modules 脳 4 columns)
  - Common dev commands (with the `python3 build.py` 鈫?`.logd` workflow front and center)
  - Coding conventions
  - Known pitfalls
  - "Where to start" per module
  - Build diagnostic workflow
  - See also (README, ARCHITECTURE, etc.)
- New `check_claude_md.py` 鈥?minimal markdown sanity check (H1, code-fence balance, empty link targets, line cap). Run as `python3 check_claude_md.py CLAUDE.md`.

Tone matches the repo's existing voice: terse, dry, slightly self-deprecating ("Yes, that many languages. No, you don't need to install all of them.").

## Testing

```sh
python3 check_claude_md.py CLAUDE.md
# Errors: none
# Total lines: 126
# Total chars: 5704
```

```sh
python3 build.py
ls diagnostic/
# build-XXXXXXXX.logd, build-XXXXXXXX.json
```

(Diagnostic artifacts will be re-generated in the actual PR with this branch's commit hash; the local stub is from the prior commit.)

## Checklist

- [x] Relevant modules affected by these changes build locally (no source changes; docs only)
- [x] Tests pass locally (markdown linter passes)
- [ ] Diagnostic build log is committed in this PR 鈥?pending: regenerate against this branch's commit
- [x] Documentation has been updated, if applicable (this is documentation)
- [ ] Configuration or schema changes are documented, if applicable
- [x] No generated build artifacts are committed, except the required diagnostic build log
- [x] Changes are scoped to the PR purpose and avoid unrelated cleanup
- [x] Security, privacy, and error-handling implications have been considered (none)

---

- [ ] I would like to request that my diagnostic build log is removed before merging

