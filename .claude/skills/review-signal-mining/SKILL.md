---
name: review-signal-mining
description: Mine large, noisy corpora of app reviews, ratings, and support tickets for latent (unstated) user needs rather than surface-level complaint frequency. Use when analyzing reviews/tickets from sealuzh/app_reviews, Play Store, Trustpilot, or support-ticket datasets to find second-order patterns, not when a simple sentiment summary is what's asked for.
---

# Review & Ticket Signal Mining

Adapted from [nexscope-ai's product-review-analysis](https://claudemarketplaces.com/skills/nexscope-ai/ecommerce-skills/product-review-analysis),
rebuilt for this project: dropped the e-commerce/marketing framing (no
Amazon/Shopify positioning language, no "marketing message" outputs) and
replaced its report format with the need/confidence/evidence/verdict schema
this project actually requires. Keep from the original: the discipline of
categorizing by root cause, tracking frequency *and* severity separately, and
never skipping straight to recommendations without the evidence layer.

**The failure mode to actively avoid**: producing a ranked list of the most
frequent complaints. That is a summary, not an inference, and it scores
poorly against this project's mission — anyone can read a review and count
words. The job is to find needs users didn't say out loud.

## Step 1 — Normalize the corpus

Every source has a different schema. Before anything else, map each row to:

```json
{
  "id": "trustpilot:kerassy:row_48213",
  "source": "trustpilot | play_store | app_reviews | support_ticket",
  "rating": 3,
  "text": "...",
  "date": "2026-04-01",
  "product": "resolved app/company name"
}
```

`id` must be traceable back to the original row (dataset name + row index or
native ID) — this is what every gap's evidence trace will cite. Never cite a
paraphrase without the `id` behind it.

## Step 2 — Read for what a frequency count misses

Frequency counting catches what people complain about most. Latent needs
hide in these second-order patterns instead:

- **Workaround language**: "I have to X every time before I can Y", "the
  trick is to...", "what I do is..." — a workaround implies a missing feature
  the user never explicitly requested because they've normalized around it.
- **Comparison/switching language**: "switched from X because...", "X does
  this better", "wish it worked like X" — reveals a need defined by absence
  relative to a competitor, not a direct ask.
- **Sentiment-behavior mismatch**: a 4–5 star review that still describes
  friction ("love it, just annoying that I have to...") — users rate the
  product on its core value while quietly tolerating a real gap. These are
  higher-signal than 1-star rants because the user isn't venting, they're
  reporting.
- **The information-dense middle**: 3-star reviews are disproportionately
  useful — too invested to leave, not happy enough to gush, so they explain
  *why* in detail. Don't let 1-star and 5-star volume drown them out.
- **Churn-adjacent language**: "uninstalling", "cancelling", "moving to
  [competitor]", "this is the last straw" — weight these higher regardless of
  raw frequency; one churn signal repeated by a small but consistent cluster
  can outweigh a hundred low-stakes 2-star gripes about something users
  tolerate long-term.
- **Absence as a signal**: if a feature category is central to the product's
  category (e.g., "sync" for a notes app) and it is essentially never
  mentioned across an otherwise vocal corpus, that's worth flagging as an
  assumption worth checking, not proof of satisfaction — but treat this as
  lower-confidence than a directly-stated pattern, and say so.
- **Support ticket root-cause vs. category**: tickets are usually pre-bucketed
  into shallow categories ("billing", "bug") by the support tool. Read ticket
  *bodies*, not just categories — the same root cause often spans multiple
  categories, and that cross-category recurrence is itself a signal a
  single-category complaint count would miss.

## Step 3 — Cluster by root cause, not by surface topic

Two complaints with different surface wording ("app is slow to load photos"
and "crashes when I have a lot of files") can share one root cause (memory
handling with large media libraries). Group by the underlying mechanism you
infer, and only after that, quantify frequency within the cluster. State the
inferred mechanism explicitly and flag it as an inference, not an observed
fact from the text.

## Step 4 — Quantify without inventing precision

For each candidate latent-need cluster, record:

- **Signal count**: how many distinct evidence IDs support it.
- **Source diversity**: how many of the available corpora/platforms show the
  same pattern independently (one source repeating itself is weaker than two
  unrelated sources converging).
- **Time spread**: is this a recent shift or a years-long standing pattern?
  Recent spikes and long-standing patterns are both meaningful, but for
  different reasons — say which one you found.
- **Contradicting evidence**: actively search for reviews that contradict the
  inferred need (e.g., users praising the exact thing you think is missing).
  Report contradictions found, don't hide them.

Hand this off to the `calibrated-evidence-synthesis` skill for the actual
confidence scoring — don't assign a confidence number here without following
that rubric.

## What NOT to do

- Don't output a "top complaints by frequency" table as the deliverable —
  that's the explicitly disallowed summarizer failure mode.
- Don't quote or cite a review/ticket you didn't actually see in the data.
- Don't collapse sarcasm into literal sentiment (a sarcastic 5-star review
  praising how "great" a bug is is a strong complaint, not a positive
  signal) — but flag sarcasm detection as inherently uncertain and lower
  confidence accordingly rather than treating it as settled.
