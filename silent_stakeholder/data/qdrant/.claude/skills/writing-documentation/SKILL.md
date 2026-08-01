---
name: writing-documentation
description: Write and update README files, module/function docstrings, and other user- or developer-facing documentation. Use when asked to document code, update the README, write usage instructions, or explain how a feature works to future readers.
---

# Writing Documentation

## Quick start

1. Identify the audience: end user (README, usage docs) vs. developer
   (docstrings, inline architecture notes) vs. future agent (`CLAUDE.md`).
2. Write for someone with no prior context on this specific change, but who
   knows the general domain — don't over-explain basics, do explain
   project-specific decisions.
3. Keep examples runnable and accurate — verify commands actually work before
   documenting them.
4. Update documentation in the same change as the code it describes; stale
   docs are worse than no docs.

## README structure (for this project)

```markdown
# Project Name

One-paragraph description of what this does and why it exists.

## Installation

[exact, verified commands]

## Usage

[minimal working example]

## Development

[how to run tests, lint, contribute]
```

## Docstring style

Use one-line summary + optional details, Google/NumPy-style args when the
signature isn't self-explanatory:

```python
def fetch_records(source: str, *, limit: int = 100) -> list[Record]:
    """Fetch up to `limit` records from `source`.

    Raises:
        ConnectionError: if `source` is unreachable.
    """
```

Don't write a docstring that just restates the function name
(`"""Fetches records."""` on `fetch_records` adds nothing — explain
constraints, side effects, or exceptions instead).

## Checklist

- [ ] Audience identified and content matches it
- [ ] Commands/examples verified, not assumed
- [ ] No stale references to removed code/flags
- [ ] Docstrings explain non-obvious behavior, not the obvious
- [ ] Updated alongside the code change, not deferred
