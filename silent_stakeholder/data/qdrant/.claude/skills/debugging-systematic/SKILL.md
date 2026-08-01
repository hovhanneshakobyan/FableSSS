---
name: debugging-systematic
description: Systematically root-cause bugs, test failures, and unexpected runtime behavior using evidence rather than guesswork. Use when investigating an error, exception, failing test, crash, or behavior that doesn't match expectations.
---

# Systematic Debugging

## Quick start

1. **Reproduce first.** Get a minimal, reliable way to trigger the failure
   (a failing test, a script, a command) before changing any code.
2. **Read the full error.** Capture the exact traceback/stack trace, not a
   paraphrase. The real line numbers and exception types matter.
3. **Form a hypothesis** about the root cause before editing code. State it
   explicitly ("I believe X because Y").
4. **Gather evidence** to confirm or reject the hypothesis: add targeted
   `print`/logging, inspect variable state, or write a tiny isolated repro
   script. Prefer evidence over speculative fixes.
5. **Fix the root cause**, not the symptom. If a null check "fixes" a crash
   but the null shouldn't be possible, find why it's null.
6. **Verify** by re-running the original repro/test, then run the broader
   test suite to check for regressions.

## Checklist

- [ ] Reproduced reliably
- [ ] Full error/traceback captured verbatim
- [ ] Hypothesis stated before editing
- [ ] Evidence gathered (not just guessed)
- [ ] Root cause fixed (not just the symptom)
- [ ] Original repro passes
- [ ] Full test suite passes (`pytest`)
- [ ] Regression test added covering this bug

## Common Python failure classes and where to look first

- **`AttributeError`/`TypeError` on `None`** → trace back where the value was
  supposed to be set; check for an early return or missing initialization.
- **Off-by-one / index errors** → check loop bounds and slicing (`[:-1]` vs `[:]`).
- **Mutable default argument bugs** → look for `def f(x=[])` patterns.
- **Import errors / circular imports** → check module import order, not just
  `sys.path`.
- **Flaky tests** → check for shared mutable state, unseeded randomness, or
  reliance on execution order between tests.

## When stuck

If two or three targeted attempts don't resolve it, stop and widen the
investigation: check recent commits (`git log -p -- <file>`), diff against a
known-good state, or add more granular logging around the suspected boundary
rather than repeatedly guessing at fixes.
