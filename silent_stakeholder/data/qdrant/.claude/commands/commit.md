---
description: Stage relevant changes and create a Conventional Commits-formatted commit
---

Follow the `git-conventional-commits` skill.

1. Run `git status` and `git diff` (and `git diff --staged` if anything is
   already staged) to see the full set of changes.
2. Identify which changes form one logical unit. If unrelated changes are
   mixed together, tell the user and propose splitting into multiple commits
   instead of bundling them.
3. Stage the relevant files with `git add`.
4. Draft a Conventional Commits message (type(scope): summary, plus body if
   the "why" isn't obvious from the diff).
5. Commit using a heredoc so multi-line messages format correctly.
6. Run `git status` to confirm the commit succeeded.

Do not push. Do not use `--amend` unless the user explicitly asks or a
pre-commit hook modified files from a commit made earlier in this session.
