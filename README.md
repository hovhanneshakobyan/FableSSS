#THE SILENT STAKEHOLDER — YOUR MISSION

Every product has a stakeholder who never files a ticket, never joins sprint planning, never gets a seat in the room: the user whose real need quietly diverges from what the team is building.

Complaints are easy — anyone can read a review.
Your job: surface the needs users DIDN'T say out loud — and prove you're right.

━━━━━━━━━━━━━━━━━━
WHAT YOU WORK WITH

You assemble two sides of ONE real product from the open datasets below:

What the team is BUILDING — roadmap / backlog (a product's GitHub issues + milestones = planned features, epics, priorities)
What users are SIGNALING — a large, noisy corpus: reviews, support tickets, feedback, churn notes. Expect contradictions, duplicates, sarcasm, conflicting requests. Cutting through that is part of the work.

DATA SOURCES:
- Reviews → huggingface.co/datasets/sealuzh/app_reviews 
- Reviews → kaggle.com/datasets/dmytrobuhai/play-market-2025-1m-reviews-500-titles
- Reviews → huggingface.co/datasets/Kerassy/trustpilot-reviews-123k
- Tickets → kaggle.com/datasets/mirzayasirabdullah07/customer-support-tickets-dataset-200k-records
- Tickets → huggingface.co/datasets/Tobi-Bueck/customer-support-tickets
- Backlog → GitHub issues + milestones via api.github.com
Pick ONE app. Pull its reviews AND its GitHub roadmap. Same product, both sides.

━━━━━━━━━━━━━━━━━━

WHAT YOU BUILD

An AI system that reads across both sources and surfaces the TOP 3–5 unmet needs the roadmap is missing or under-serving.

NOT a summarizer. Listing frequent complaints scores poorly. The value is inferring LATENT needs — the ones that only show up as second-order patterns.

For EVERY gap, produce all four 
The need — clearly, in the user's terms
A confidence score — calibrated, not decorative. 90%-sure and 55%-sure must differ, and you must justify the number
Evidence trace — every gap links to the specific signals that support it (by ID). No evidence, no gap
Gap verdict — is it IGNORED, UNDER-PRIORITIZED, or MISUNDERSTOOD by the roadmap?

Output ranked by strength of evidence, strongest first.

━━━━━━━━━━━━━━━━━━

HOW YOU'RE SCORED

Two layers — you need both:

 Correctness & rigor — every gap must be provable from your data. Plausible-but-wrong gaps hurt you; missing obvious ones hurts you. Judges follow your evidence trace.
Live defense — you answer on the spot: "Why rank this #1?" "Here's a gap you missed — why?" "Defend this confidence score." If you can't reason about your output, you built a demo, not a system.

━━━━━━━━━━━━━━━━━━

THE BAR

Anyone can tell us what users complained about.
WIN by telling us what users needed and never said — and proving it from the data.
Clock runs 11:40 → 12:00 tomorrow. Go build.
