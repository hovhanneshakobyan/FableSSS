---
name: security-review
description: Review code changes for security vulnerabilities specific to a Python data pipeline that ingests untrusted third-party text (reviews, tickets, GitHub content) and calls LLM APIs. Use when reviewing a diff before merge, or when the user asks for a security review of pending changes.
---

# Security Review (data/LLM pipeline)

Adapted from [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review).
The upstream review targets general web-app vulnerability classes (SQLi,
XSS, auth bypass). Most of those don't apply to this project — there's no
web server or auth layer here. What upstream gets right and this skill
keeps: **high-confidence-only findings**, explicit exclusions to avoid noise,
and a required severity + exploit-scenario + fix format. What's retargeted:
the vulnerability categories, to match an actual threat model of "ingest
huge amounts of untrusted scraped/downloaded text and user-generated
content, then feed it to LLM APIs and file operations."

Use the `/security-review` command (`.claude/commands/security-review.md`)
to run this against the current diff.

## Threat model for this project

- **Untrusted text everywhere**: review text, support ticket bodies, and
  GitHub issue bodies are all attacker-reachable in principle (anyone can
  post a review or open an issue). Treat all of it as untrusted input.
- **LLM prompt injection**: if any code assembles prompts by concatenating
  raw review/ticket/issue text with instructions, a review author could embed
  text like "ignore previous instructions and output X" aimed at manipulating
  the analysis. This is the single highest-relevance category here.
- **Secrets**: `GITHUB_TOKEN`, HF tokens, Kaggle API credentials, and any LLM
  API keys must never be hardcoded, logged, or committed.
- **Archive/dataset handling**: downloaded datasets (Kaggle zips, HF
  snapshots) get extracted locally — zip-slip (path traversal via `../` in
  archive entry names) and unsafe deserialization (never `pickle.load` on
  downloaded/untrusted files) are real risks here.
- **PII in support ticket data**: ticket datasets can contain real user PII
  (names, emails, account details). Sending raw PII to a third-party LLM API
  or writing it unredacted into any output artifact is a data-handling risk.

## Categories to examine

**Prompt injection**
- Is untrusted text (review/ticket/issue body) ever concatenated directly
  into a system/instruction prompt without delimiting or without the model
  being told that content is untrusted data, not instructions?
- Does any downstream code *act* on text extracted from within the untrusted
  content (e.g., parsing an "instruction" out of a review and executing it)?

**Secrets management**
- Any hardcoded API key, token, or credential in source, config, or example
  files?
- Are secrets loaded only from environment variables / `.env` (gitignored),
  never printed in logs, exceptions, or debug output?

**Archive & file handling**
- When extracting a zip/tar from a downloaded dataset, is each entry's
  resolved path validated to stay inside the target directory (no `../`
  traversal)?
- Is `pickle`, `eval`, `exec`, or `yaml.load` (unsafe loader) ever used on
  data that originated outside this codebase? Use `yaml.safe_load`,
  `json`, or `pandas`/`pyarrow` readers instead.

**PII handling**
- Does ticket/review data get written to logs, cache files, or committed
  fixtures with PII intact?
- Is PII redacted or excluded before being sent to an external LLM API,
  where that matters for the project's data-handling commitments?

**Dependency/network safety**
- Are external URLs (dataset download links, GitHub API calls) built from
  any untrusted input, or are they fixed/validated?

## Exclusions (don't report these — noise, not signal, for this project)

- Theoretical DoS/resource exhaustion from large datasets.
- Missing input validation on fields with no security consequence.
- Style/formatting issues — that's `ruff`'s job, not this skill's.
- Vulnerabilities in third-party dataset content itself (e.g., a review
  containing malicious text is expected input, not a code vulnerability,
  unless the code fails to treat it as untrusted).
- Outdated dependency versions — track those separately, not as a
  vulnerability finding here.

## Output format

```
# Finding N: <short title> — `path/to/file.py:LINE`

- Severity: High | Medium | Low
- Category: prompt_injection | secrets | path_traversal | unsafe_deserialization | pii_exposure
- Confidence: 0.0–1.0 (only report ≥0.7)
- Description: what's wrong and why
- Exploit scenario: concretely, what a malicious review/ticket/issue author
  could achieve
- Fix: specific recommendation
```

Only report findings you're ≥70% confident are real and exploitable in this
project's context. Better to under-report than to flood a two-person hackathon
team with speculative noise.
