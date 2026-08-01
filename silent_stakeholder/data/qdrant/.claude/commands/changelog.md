---
description: Add a changelog entry for the most recent change under [Unreleased]
argument-hint: "[Added|Changed|Fixed|Removed] description (optional; inferred from diff if omitted)"
---

Follow the `changelog-maintenance` skill.

1. If `$ARGUMENTS` specifies a category and description, use it directly.
   Otherwise infer both from `git diff` / `git diff --staged` / the most
   recent commit.
2. If `CHANGELOG.md` doesn't exist, create it with the Keep a Changelog
   structure.
3. Add one concise, user-facing line under the correct category in
   `[Unreleased]`, creating that category heading if it's missing.
