---
description: Draft a pull request title and description from the current branch's commits and diff
argument-hint: "[base-branch] (optional, defaults to main)"
---

1. Determine the base branch (use `$ARGUMENTS` if given, otherwise `main`).
2. Run `git log <base>..HEAD` and `git diff <base>...HEAD` to see every
   commit and change that will be included — not just the latest commit.
3. Draft:
   - A concise, descriptive PR title.
   - A `## Summary` section with 1-3 bullet points on *why* the change was
     made.
   - A `## Test plan` section listing concrete verification steps
     (commands run, scenarios checked).
4. Present the draft to the user. Only run `gh pr create` if explicitly asked
   to actually open the PR.
