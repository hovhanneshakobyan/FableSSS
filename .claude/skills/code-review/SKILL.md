---
name: code-review
description: Review code changes, diffs, or pull requests for correctness, security, readability, and maintainability. Use when reviewing a diff, examining a pull request, or when the user asks for a code review of recent changes.
---

# Code Review

## Quick start

1. Identify the scope: `git diff` (unstaged), `git diff --staged`, or
   `git diff <base>...HEAD` for a full branch/PR.
2. Understand intent first — read the commit messages/PR description before
   judging the diff line by line.
3. Work through the checklist below.
4. Report findings grouped by severity, with file:line references.

## Review checklist

- [ ] **Correctness**: logic matches intent; edge cases (empty input, `None`,
      boundary values, concurrent access) are handled.
- [ ] **Security**: no injected/unsanitized input into shell/SQL/HTML; no
      secrets or credentials committed; no unsafe deserialization.
- [ ] **Error handling**: exceptions are specific and handled at the right
      layer; no silent `except: pass`.
- [ ] **Tests**: new behavior has tests; bug fixes have regression tests.
- [ ] **Readability**: names are clear; functions are focused; no dead code
      or leftover debug prints.
- [ ] **Consistency**: follows this repo's conventions (see `CLAUDE.md`) —
      type hints, docstrings, formatting via `ruff`.
- [ ] **Scope**: the diff does one logical thing; unrelated changes are
      flagged for splitting out.

## Feedback format

```
🔴 Critical — must fix before merge
🟡 Suggestion — worth addressing
🟢 Nit — optional polish
```

Cite the exact file and line range for each finding using the code reference
format, and explain *why* it matters, not just *what* to change.

## What not to do

- Don't nitpick pure style choices already enforced by `ruff format`.
- Don't request changes without a concrete reason ("this could be better"
  without specifics isn't actionable).
- Don't approve silently if there's a correctness or security concern —
  always surface it, even if the fix is small.
