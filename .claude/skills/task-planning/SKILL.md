---
name: task-planning
description: Break a feature request or large task into a concrete, ordered implementation plan with tracked steps. Use when a request spans multiple files or steps, is ambiguous in scope, or before starting any non-trivial multi-step implementation.
---

# Task Planning & Breakdown

## Quick start

1. **Clarify scope first.** If the request has multiple reasonable
   interpretations or significant trade-offs, ask before planning further
   rather than guessing.
2. **Decompose into steps** that are each independently verifiable (can be
   tested/reviewed on their own), ordered by dependency.
3. **Identify unknowns explicitly** — call out anything that needs
   investigation before it can be planned precisely, and investigate it
   before finalizing the plan.
4. **Size the plan to the task.** A one-file bug fix doesn't need a plan; a
   new feature touching several modules does.
5. **Track progress** using a todo list, one item per step, updating status
   as you go — only one step in progress at a time.

## Plan structure

```markdown
## Goal
[One sentence: what "done" looks like.]

## Steps
1. [Step] — [why it's needed / what it unblocks]
2. [Step]
3. [Step]

## Open questions / risks
- [Anything uncertain, and how it will be resolved]

## Out of scope
- [Explicitly excluded, to prevent scope creep]
```

## Breaking down feature requests

Split by **vertical slices** (a thin end-to-end path through the system)
rather than horizontal layers, when possible — this keeps each step
demonstrably working rather than leaving half-built layers with nothing to
verify until the very end.

## Checklist

- [ ] Scope clarified with the user if ambiguous
- [ ] Steps are independently verifiable and ordered by dependency
- [ ] Unknowns/risks called out explicitly, not glossed over
- [ ] Plan size matches task complexity (no over-planning trivial work)
- [ ] Progress tracked step by step, not all-at-once at the end
