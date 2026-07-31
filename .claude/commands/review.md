---
description: Review the current diff (uncommitted changes or branch vs base) using the code-review skill
argument-hint: "[base-branch] (optional, defaults to uncommitted changes)"
---

Follow the `code-review` skill.

If an argument is given, review `git diff $ARGUMENTS...HEAD`. Otherwise review
uncommitted changes (`git diff` plus `git diff --staged`).

Work through the full review checklist (correctness, security, error
handling, tests, readability, consistency, scope) and report findings grouped
by severity (🔴 Critical / 🟡 Suggestion / 🟢 Nit) with file:line references.
