---
description: Run a security review of pending changes, focused on this project's actual threat model (prompt injection, secrets, archive handling, PII)
allowed-tools: Bash(git diff:*), Bash(git status:*), Bash(git log:*), Read, Glob, Grep
---

Follow the `security-review` skill in `.claude/skills/security-review/SKILL.md`.

1. Determine the diff scope: uncommitted + staged changes by default, or
   `git diff <base>...HEAD` if a base branch is given as an argument.
2. Read the actual diff (`git diff`, `git diff --staged`) — never review from
   memory.
3. Walk the diff against the five threat categories in the skill: prompt
   injection, secrets management, archive/file handling, PII handling, and
   dependency/network safety. Skip everything in the skill's exclusions list.
4. Only report findings you are ≥70% confident are real and exploitable —
   this is a small hackathon project, not a large attack surface; noise is
   worse than a missed theoretical issue.
5. Output findings in the required format (file:line, severity, category,
   confidence, description, exploit scenario, fix). If there are no
   qualifying findings, say so explicitly rather than inventing minor ones.
