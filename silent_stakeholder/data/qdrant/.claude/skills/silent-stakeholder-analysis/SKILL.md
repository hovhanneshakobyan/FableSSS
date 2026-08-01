---
name: silent-stakeholder-analysis
description: End-to-end pipeline for the Silent Stakeholder mission — cross-reference a product's GitHub roadmap against its noisy review/ticket corpus to surface 3-5 latent, unstated user needs the roadmap under-serves, each with a calibrated confidence score, an evidence trace, and a gap verdict. Use when asked to run the full gap analysis, pick a product for it, or produce the final ranked report.
---

# Silent Stakeholder Analysis

Orchestrates three other skills into the exact deliverable this project's
mission requires. Read those skills for the mechanics; this skill defines
the end-to-end workflow and the final output contract.

- `github-roadmap-extraction` — pulls "what the team is building"
- `review-signal-mining` — pulls "what users are signaling"
- `calibrated-evidence-synthesis` — turns both into scored, evidence-linked,
  ranked gaps

## Workflow

```
Task Progress:
- [ ] 1. Pick ONE product present in both a review/ticket corpus and GitHub
- [ ] 2. Extract roadmap (github-roadmap-extraction)
- [ ] 3. Mine review/ticket corpus for latent-need candidates (review-signal-mining)
- [ ] 4. Cross-reference each candidate against roadmap items
- [ ] 5. Score, cite evidence, assign verdicts (calibrated-evidence-synthesis)
- [ ] 6. Self-critique pass on the full ranked list
- [ ] 7. Produce final report in the required output contract
```

### Step 1: Product selection

Pick a product that has **both** sides available:
- A public GitHub repo with Issues (and ideally Milestones) actively used —
  check recent issue activity before committing, a dead or issue-disabled
  repo kills the roadmap side.
- Meaningful review/ticket volume in at least one of the listed corpora
  (sealuzh/app_reviews, Play Market 1M reviews, Trustpilot 123k, or the
  support-ticket datasets).

Prefer a product where the two sides are genuinely the *same* product, not a
loose association (e.g., don't pair a company's marketing app reviews with
an unrelated internal tool's GitHub repo). State explicitly how you verified
they're the same product.

### Step 2–3: Extraction and mining

Run independently — don't let roadmap contents bias what you look for in the
reviews first, or you'll anchor on confirming existing roadmap items instead
of finding what's missing. Mine the review corpus for latent-need clusters
*before* cross-referencing against the roadmap in depth.

### Step 4: Cross-reference

For each latent-need cluster from Step 3, search the roadmap (Step 2) for
anything related — by keyword, by label, by reading candidate issue bodies
in full, not just titles. Record what you found (or didn't) with specific
issue `id`s.

### Step 5: Score and rank

Apply the full `calibrated-evidence-synthesis` rubric. Every finding needs:
a plain-language need statement in the user's own terms, a calibrated
confidence score with stated justification, an evidence trace of specific
IDs from both sides, and a gap verdict (IGNORED / UNDER-PRIORITIZED /
MISUNDERSTOOD).

### Step 6: Self-critique

Run the self-critique pass from `calibrated-evidence-synthesis` on the full
list before finalizing. Also sanity-check the list as a whole:
- Are the top-ranked items actually the strongest by evidence, or just the
  most narratively compelling?
- Is there an obvious gap a reviewer would immediately spot that's missing
  from the list? If so, either add it (with real evidence) or be ready to
  explain why it was considered and excluded.

### Step 7: Final output contract

```markdown
# Silent Stakeholder Analysis: <Product Name>

**Roadmap source:** <owner/repo> (N issues, M milestones analyzed)
**Signal source(s):** <dataset(s) used, N reviews / tickets analyzed, date range>

## Gap #1 — <Need, stated in the user's own terms>

- **Confidence:** XX% — <one-sentence justification citing rubric factors>
- **Verdict:** IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD
- **Evidence trace (user signal):** id1, id2, id3, ...
- **Evidence trace (roadmap):** issue id(s), or "none found" for IGNORED
- **Why this isn't just a complaint:** <the second-order reasoning that
  makes this a latent need, not a surface-level frequency count>
- **Steelman considered:** <the strongest counterargument, and why it
  didn't overturn this finding>

## Gap #2 ...

(3-5 gaps total, ranked strongest evidence first)

## Methodology notes

<Corpus sizes, normalization approach, known limitations, anything a judge
would need to evaluate rigor>
```

## Preparing for live defense

For every gap in the final list, be ready to answer on the spot:
- "Why rank this #N?" → restate the evidence-strength formula result and
  what specifically separates it from the gap above/below it.
- "Here's a gap you missed" → be ready to either find the evidence for it
  live (if it's real) or explain concretely why it didn't meet the
  evidence bar (too thin, contradicted, already well-covered by roadmap).
- "Defend this confidence score" → walk through the rubric factor by factor,
  don't just restate the number more confidently.

If you can't answer one of these from what you already recorded, that's a
sign the self-critique pass (Step 6) wasn't thorough enough — redo it rather
than improvising a justification live.

## What NOT to do

- Don't submit a complaint-frequency table as the analysis — see
  `review-signal-mining`'s explicit warning against this.
- Don't assign confidence scores without the rubric in
  `calibrated-evidence-synthesis`.
- Don't cite evidence IDs you didn't verify against the actual source data.
- Don't pick a product where the GitHub roadmap side is too sparse/inactive
  to say anything meaningful — that produces "everything is IGNORED" by
  default, which is a data selection failure, not a finding.
