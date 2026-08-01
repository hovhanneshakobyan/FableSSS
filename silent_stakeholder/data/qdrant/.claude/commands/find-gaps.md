---
description: Run the full Silent Stakeholder gap analysis for a chosen product
argument-hint: "[product name / owner-repo] (optional; if omitted, propose candidates first)"
---

Follow the `silent-stakeholder-analysis` skill end to end.

If `$ARGUMENTS` names a product, use it (confirm you can find both a GitHub
repo with active Issues and a review/ticket corpus match before proceeding —
report back if either side isn't viable instead of forcing a weak pairing).

If no product is given, propose 2-3 candidate products that plausibly have
both sides available in the listed datasets, and ask which to proceed with
before running the full pipeline.

Run all 7 steps of the skill's workflow, tracking progress with a todo list,
and produce the final report in the skill's required output contract.
