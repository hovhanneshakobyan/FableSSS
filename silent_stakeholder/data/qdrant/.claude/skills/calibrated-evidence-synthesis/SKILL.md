---
name: calibrated-evidence-synthesis
description: Apply rigorous, calibrated confidence scoring and mandatory evidence citation when synthesizing a claim (e.g. an inferred user need, a gap verdict) from multiple noisy sources. Use whenever producing a ranked finding that must survive live cross-examination — every score must be justified, every claim must cite specific evidence IDs, and unsupported claims must be dropped rather than asserted.
---

# Calibrated Evidence Synthesis

Distilled from the integrity-gate philosophy in
[Imbad0202/academic-research-skills](https://github.com/imbad0202/academic-research-skills)
(ARS) — not its paper-writing machinery, which doesn't apply here, but its
core discipline: claims must trace to verifiable sources, confidence scores
must be calibrated rather than decorative, and a structured self-critique
pass runs before anything is presented as final. ARS exists because
autonomous research pipelines hallucinate citations and fabricate support for
claims; the same failure mode applies directly to inferring "unmet needs"
from noisy review data — it is just as easy to assert a plausible-sounding
need with no real evidence behind it.

## The core rule: no evidence, no gap

Every finding must cite specific evidence IDs from the underlying data (see
`review-signal-mining` and `github-roadmap-extraction` for how those IDs are
produced). If you cannot point to at least one concrete, re-checkable ID per
side of the claim (user signal *and* roadmap state), the finding does not
ship — downgrade it to "insufficient evidence" and drop it from the ranked
output, don't include it with an apologetic low score instead.

## Confidence calibration rubric

A confidence score is a claim about how likely you'd be right if someone
independently re-derived this from the same data. Use this rubric — don't
assign round numbers by feel:

| Factor | Increases confidence | Decreases confidence |
|---|---|---|
| Signal count | Many independent evidence IDs | One or two isolated mentions |
| Source diversity | Pattern appears across ≥2 unrelated corpora (e.g. both Trustpilot and support tickets) | Only appears in a single source |
| Directness | Users state the need in their own words | Need is inferred from absence or indirect workaround language |
| Roadmap linkage clarity | Easy to determine whether an existing issue does/doesn't cover it | Roadmap item is ambiguous, or repo has poor issue hygiene (unlabeled, no milestones) |
| Contradicting evidence | None found after actively searching | Some users explicitly praise the thing you claim is missing |
| Time stability | Pattern holds across multiple time periods | Single short-lived spike, cause unclear |

**Anchor points** (don't just pick a vibe-based number — justify against
these):

- **90%+**: multiple independent sources, directly stated by users, clear
  and unambiguous roadmap status, no contradicting evidence found.
- **70–85%**: solid signal count and at least one corroborating dimension
  (source diversity OR directness OR roadmap clarity), but not all of them;
  minor contradictions exist but don't undermine the core claim.
- **55–65%**: plausible and evidence-backed, but relies on inference (absence
  patterns, workaround language) rather than direct statements, or roadmap
  status is ambiguous, or evidence comes from only one source.
- **Below 55%**: don't present as a ranked finding — mention as an open
  question if worth noting, but don't give it a confidence-scored verdict.

Every confidence score in the final output must have a one-sentence
justification referencing which rubric factors applied — "90% because two
independent sources (N reviews, M tickets) directly state this, spanning 18
months, and issue #123 exists but was closed as not_planned" is a real
justification; "90%, high confidence" is not.

## Gap verdict taxonomy

- **IGNORED** — no roadmap item, open or closed, addresses this need at all.
- **UNDER-PRIORITIZED** — a roadmap item exists and is genuinely on-target,
  but is stale, unmilestoned, low-priority-labeled, or has visible user
  demand (comments/reactions) with no action taken.
- **MISUNDERSTOOD** — a roadmap item exists and is being actively worked, but
  its scope addresses a different or narrower problem than what the evidence
  shows users actually need (e.g., team is building a symptom fix; users need
  the root cause addressed).

State which verdict applies and why, citing the specific roadmap item `id`
that grounds the verdict (or explicitly noting the absence of one, for
IGNORED).

## Self-critique pass (run before finalizing)

For every candidate finding, before it enters the final ranked list:

1. **Steelman the opposite conclusion**: what's the strongest argument this
   isn't really a gap (e.g., roadmap item X actually does cover it if read
   generously; the pattern is small-sample noise; it's addressed by a
   feature outside the tracked repo)?
2. **Check for fabrication**: re-verify every cited evidence ID actually says
   what you claim it says — don't trust your own earlier paraphrase.
3. **Adjust or drop**: if the steelman is strong, lower the confidence score
   and say so explicitly, or drop the finding entirely if the steelman
   defeats it.

Keep a short rationale log (even just informally in your working notes) of
why each finding survived this pass — you will be asked to defend rankings
live, and "I re-derived it and it held up because..." is a much stronger
answer than re-deriving it from scratch under questioning.

## Ranking rule

Rank by evidence strength, not by raw complaint volume or by how compelling
the narrative sounds: `strength ≈ signal count × source diversity ×
directness`, moderated down by any unresolved contradiction. A gap with
fewer total mentions but corroboration across two independent sources and a
clearly stale roadmap item should outrank a gap with more mentions but only
one source and an ambiguous roadmap status.
