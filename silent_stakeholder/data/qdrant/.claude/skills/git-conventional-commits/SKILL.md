---
name: git-conventional-commits
description: Write Conventional Commits-formatted commit messages and follow this repo's git branching/workflow conventions. Use when creating a commit, writing a commit message, or asked to describe staged changes.
---

# Git Workflow & Conventional Commits

## Commit message format

```
<type>(<optional scope>): <short summary, imperative mood, no period>

<optional body: why, not what — the diff already shows what>

<optional footer: BREAKING CHANGE:, Closes #123>
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `style`, `ci`,
`build`, `revert`.

## Examples

Input: added retry logic to the API client
Output:
```
feat(client): add exponential backoff retry to API requests

Requests were failing on transient 5xx errors with no retry, causing
avoidable job failures. Retries up to 3 times with jittered backoff.
```

Input: fixed off-by-one in pagination
Output:
```
fix(pagination): correct last-page item count

The final page dropped one item because the slice used `page_size` instead
of the remaining item count.
```

Input: renamed `get_data` to `fetch_records`
Output:
```
refactor(api): rename get_data to fetch_records for clarity
```

## Workflow rules

- One logical change per commit; don't bundle an unrelated refactor with a
  behavior change.
- Write the summary in imperative mood ("add", not "added"/"adds").
- Look at the actual staged diff (`git diff --staged`) before writing the
  message — never guess at what changed.
- Never commit secrets, `.env` files, or credentials.
- Never `git push --force` to `main`/`master`.
- Only commit when explicitly asked to.

## Before committing

1. `git status` — confirm what's staged/unstaged.
2. `git diff --staged` — read the actual changes.
3. Draft the message using the format above.
4. `git commit -m "..."` (use a heredoc for multi-line messages).
5. `git status` again to confirm success.
