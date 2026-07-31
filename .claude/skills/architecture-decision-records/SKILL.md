---
name: architecture-decision-records
description: Write Architecture Decision Records (ADRs) documenting significant technical decisions and their rationale. Use when a non-trivial architectural or technology choice is made (framework, data model, API design, dependency) that future contributors would need context on.
---

# Architecture Decision Records (ADRs)

## When to write one

Write an ADR for decisions that are costly to reverse or non-obvious in
hindsight: choice of framework/library, data storage approach, API contract
shape, major module boundaries, or rejecting an apparently-reasonable
alternative. Skip it for routine implementation details already clear from
the code.

## Location & naming

Store under `docs/adr/NNNN-short-title.md`, zero-padded, sequential
(`0001-use-pytest-for-testing.md`). Create the `docs/adr/` directory if it
doesn't exist yet.

## Template

```markdown
# NNNN. Short title in imperative mood

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by NNNN | Deprecated

## Context

What problem or force is driving this decision? What constraints apply?

## Decision

What was decided, stated plainly.

## Consequences

What becomes easier or harder as a result. Include real trade-offs, not just
upsides — a decision with no downsides usually means the alternatives weren't
seriously considered.

## Alternatives considered

- **Option A** — why it was rejected.
- **Option B** — why it was rejected.
```

## Checklist

- [ ] Decision is significant/hard to reverse (not routine)
- [ ] Context explains the actual constraint, not just "we needed X"
- [ ] Consequences include real trade-offs
- [ ] At least one rejected alternative is documented with a reason
- [ ] Status is set and sequential number doesn't collide with an existing ADR
