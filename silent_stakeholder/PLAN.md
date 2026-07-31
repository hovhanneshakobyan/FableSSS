# The Silent Stakeholder — Architecture & Build Plan

**Product:** K-9 Mail (`com.fsck.k9`) · **Demo:** 11:40–12:00
**Thesis:** On a mature backlog the gap is not *absence*, it is *misframing*.

---

## 0. Verified ground truth (recompute before quoting; do not trust prose)

| Fact | Value |
|---|---|
| Reviews | **1,560**, `2015-11-29 → 2017-05-02` |
| Stars | 1★277 2★205 3★223 4★282 5★573 (mean 3.43) |
| Issues | **1,718**, `2015-03-15 → 2017-12-31`, 1,708 with bodies |
| Issue state | 1,552 closed / **166 open in 2026** |
| Milestone-tagged issues | 259 |
| Labeled sentences | **4,224** covering all 1,560 reviews |

Epics in-window: Design Overhaul 55 · **Mail synchronization 31** · PGP/MIME 24 ·
Notifications 17 · Do it properly 12 · Onboarding 10

Sentence labels (third-party, from the dataset authors — *not ours*):
PROBLEM DISCOVERY 508 · INFORMATION GIVING 361 · FEATURE REQUEST 209 ·
INFORMATION SEEKING 70 · OTHER 3,076. **120 PROBLEM DISCOVERY sentences come from
4–5★ reviewers** — the happy-but-broken pool, externally labeled.

### The money shot (verified against all 1,718 issues)

| Term set | Rev | Iss | Polarity |
|---|---|---|---|
| `battery/drain/power` | 53 | 30 | **1.95× user** |
| `"syncing disabled"` | 40 | 14 | **3.15× user** |
| `doze/jobscheduler/wakelock` | 5 | 14 | 0.39× dev |
| `IMAP idle` | **2** | **22** | **0.10× dev** |

Bridge (both vocabularies co-occur): **21 issues + 10 reviews**.
Evidence IDs: `f69170c3` (1★ 2016-10-11 Doze), `e81147dd` (2★ 2016-10-27),
`e70248d7` (3★ 2016-10-28 Nougat), issues `#2890`, `#2805`.

---

## 1. Architecture decisions

| Question | Decision | Why |
|---|---|---|
| **Backend?** | **None.** CLI + one self-contained HTML file. | Flask/FastAPI not installed. A server is a process that can die on stage. |
| **RAG / vector DB?** | **No.** | Corpus ≈ 370K tokens — fits in one Opus 5 prompt. Worse: embeddings cluster by lexical similarity, so they would *systematically miss* the symptom↔mechanism pairs the engine exists to find, then mislabel MISUNDERSTOOD as IGNORED. |
| **Database?** | **SQLite** + FTS5 (porter). | Present, zero install, one portable file. `issues.number INTEGER PRIMARY KEY` == rowid → fastest evidence lookup. |
| **Clustering?** | sklearn TF-IDF + KMeans (installed). | Offline, instant on 1,560 docs. |
| **LLM calls?** | `claude-opus-5`, 3 stages only. | Everything else deterministic and recomputable. |

**Anthropic API rules that will bite you:**
- Thinking is **ON by default** on `claude-opus-5` — do not pass `thinking`.
- `budget_tokens`, `temperature`, `top_p` → **400**. Assistant prefill → **400**.
- `max_tokens` caps thinking **plus** text. Use 16000, stream above that.
- `output_config={"effort": "high"}` (S3/S6), `"xhigh"` (S4).
- Structured output: `additionalProperties:false` + full `required`; **no** `minLength`/`minimum`/recursive. Prefer `client.messages.parse()` with Pydantic.
- Prompt-cache the corpus block; `cache_control` on the **last system block**, varying question after. Verify with `usage.cache_read_input_tokens`.
- **Never interpolate a timestamp into the system prompt** — kills the cache.

---

## 2. Pipeline

```
S0  ingest              deterministic   DONE — data/raw/*.json
S1  normalize + join    deterministic   reviews + issues + sentences -> SQLite
S2  signal extraction   deterministic   6 latent-need families
S3  candidate synthesis LLM  x1         ~30 candidate themes
S4  mechanism bridging  LLM proposes -> CODE VERIFIES     <- core IP
S5  scoring + verdicts  deterministic   formula below
S6  adversarial critic  LLM  x1/gap     kill/downgrade/survive
S7  rank + render       deterministic   report.html
```

**S4 is the whole design.** The LLM proposes candidate causal mechanisms and the
engineer-vocabulary terms for them. Its output is then **discarded as a claim and
used only as a query** — every term is counted deterministically over the corpus.
The model never sees a count and never asserts one.

> On stage: *"The model generated the hypothesis. The corpus scored it."*

---

## 3. Latent-need signal families (densities measured on real data)

| # | Family | Why latent | n |
|---|---|---|---|
| F1 | Workaround language | User already solved it → never files it | 77 (4.9%) |
| F2 | Happy-but-friction (4–5★ + contrast connective) | Net-satisfied → never escalates | 162 |
| F3 | Regression ("used to", "since the update") | Names a change in the world, not a feature gap | 166, mean★ **2.39** |
| F4 | Tenure + defection | Tolerance threshold crossed | 135 / 47 |
| F5 | Competitor comparison | Names capability by pointing at it | 135 |
| F6 | Conditional praise ("5 stars if…") | User has *priced* the gap | 52 |
| F0 | `sentences.csv` PROBLEM_DISCOVERY / FEATURE_REQUEST | **Third-party label** | 508 / 209 |

`λ(r) = Σ w_f · 1[f matches r]`, w = {F1 1.0, F2 1.0, F3 0.9, F4 0.8, F5 0.6, F6 1.0}.
This is what stops the engine degenerating into a frequency counter.

---

## 4. Framing-mismatch detector — Polarity Inversion Index

```
p_R(T) = reviews matching T / 1560
p_I(T) = issues  matching T / 1718
pol(T) = p_R / max(p_I, 1/1718)
PII    = log2( pol(symptom) / pol(mechanism) )     PII_norm = clip(PII/4, 0, 1)
```

**Three mandatory gates** before MISUNDERSTOOD may be assigned:
1. `PII >= 1.0`
2. `bridge >= 3` — docs where symptom AND mechanism co-occur, **cited by ID**
3. Dated external event (Android release etc.), user onset not leading it

Battery vs IMAP-idle: `PII = log2(1.95/0.10) = 4.29`, bridge = 31. Passes.

---

## 5. Verdicts (priority labels do NOT exist in-window — 0/1718)

First match wins:

```
framing gate passed + epic exists + epic term ∉ mechanism  -> MISUNDERSTOOD
|L| == 0, or |L| <= 2 with >= 40 reviews                   -> IGNORED
not_planned >= 30% or needs_information >= 40%             -> IGNORED
stale_frac >= 30%   (open in 2026)                         -> UNDER-PRIORITIZED
no epic + >= 60 reviews + star_deficit <= -0.3             -> UNDER-PRIORITIZED
else                                                        -> UNDER-PRIORITIZED
```

Print the counts that produced every verdict: `UNDER-PRIORITIZED (|L|=14, stale=5/14=0.36, |E|=0)`.
Cap at **2 MISUNDERSTOOD** in the final set; more means the gate is too loose.

---

## 6. Confidence

```
Confidence = round(100 * (0.55*E + 0.45*L)) - P        clip [5, 95]

E = 0.30*Support + 0.20*Dispersion + 0.25*Friction + 0.25*Quality
    Support    = min(1, ln(1+n)/ln(101))
    Dispersion = (months_hit/18) * (1 - max_month_share)
    Friction   = MAX(star_deficit/1.0, happy_friction_share/0.40)   <- max, not sum
    Quality    = share >=120ch AND has PROBLEM_DISCOVERY/FEATURE_REQUEST sentence

L = 0.35*PII_norm + 0.25*Recurrence + 0.25*Mechanism + 0.15*EpicAbsence
    Recurrence = share of reviews dated AFTER median closed_at of linked issues
    Mechanism  = 1.0 dated | 0.5 undated | 0.0 none

P: -15 burst (>35% one month) | -20 DiD failure | -12 critic material
   -10 backlog coverage hole  | -8 mechanism date = guess
```

**What makes confidence LOW** (say this before a judge asks): polarity ≤ 1 (known,
not latent) · no dated mechanism (unfalsifiable) · bridge < 3 (link asserted, not
witnessed) · >35% of evidence in one month (event, not need).

**Honesty beat that wins rigor points:** difference-in-differences around Nougat
came back **+0.02** — the cluster did *not* deteriorate faster than the app overall.
Say so: *"the strength rests on level, not trend — 13.3% prevalence sustained
across 17 of 18 months at a −0.55 star deficit."*

Ranking: `0.50*Conf + 0.20*L + 0.15*traceability + 0.10*friction + 0.05*verdict_bonus`.
**Ship 4 gaps, not 5.** Every extra gap is another surface to attack.

---

## 7. Anti-false-positive

1. **Adversarial critic** (LLM, hostile prompt): restatement? already-covered issue?
   falsifiable mechanism? timeline violation? sampling artifact? cherry-picking?
   → `kill` drops it, `material` costs −12 and prints a required rebuttal line.
2. **Leave-one-month-out**: recompute 18×; if `max−min > 15`, auto burst penalty.
3. **Negative control**: run the whole pipeline unchanged on AntennaPod
   (`data/raw/ap_issues.json`). It must surface **zero** Doze-shaped gaps.
   *"How do we know this isn't pattern-matching? We ran it on a podcast app. Nothing."*

---

## 8. Delivery

Single `dist/report.html`, opened from `file://`, all CSS/JS/data **inlined**.

> ⚠️ `fetch()` is blocked under `file://`. Inline the corpus in
> `<script type="application/json">`. This is the #1 way the build fails.

Two panes: ranked gaps left, evidence right. Evidence text rendered **inline** —
click gap → read the actual review with its UUID in under 2 seconds. Every ID is a
clickable token. Always show the denominator ("172 reviews, 11.0% of 1,560").
"4–5★ only" is a headline toggle, not a buried filter.

**Defense console** (`/` key, client-side, <50ms) returns one of four banners —
all four are good answers:
- **SURFACED** → jumps to the gap
- **CONSIDERED & REJECTED** → candidate id, score, *failing component*, sample IDs
- **BELOW THRESHOLD** → raw corpus scan, n, %, mean★ vs 3.43, top 10 verbatims
- **NOT IN CORPUS** → *"0 user mentions, 14 issues. That's the inverse of a gap."*

`candidates.json` must contain **every** rejected candidate with its `query_terms`.
That file is how you answer "here's a gap you missed."

**Safety net:** render all 1,560 reviews into the page so Cmd-F works even if JS dies.

---

## 9. Build order

| # | Task | Est |
|---|---|---|
| 0 | ✅ Data pulled to `data/raw/` | done |
| 1 | SQLite schema + ingest (reviews, issues, sentences, labels, milestones) | 60m |
| 2 | S2 signal families + derived columns (freeze `AS_OF`) | 40m |
| 3 | Polarity/bridge/PII deterministic layer | 45m |
| 4 | Scoring + verdicts + ranking | 40m |
| 5 | `render.py` → report.html with inline evidence | 90m |
| 6 | Defense console + rejected candidates | 75m |
| 7 | S3/S4/S6 LLM stages | 60m |
| 8 | Negative control on AntennaPod | 20m |
| 9 | PDF, 2nd laptop, USB, adversarial rehearsal | 45m |

**Cut line — if 90 minutes remain:** ingest + §3 polarity + hand-write 4 gap
narratives from the top rows + render one HTML with inline evidence + full corpus
dump. **The Doze finding lives in the counts, not the model** — it survives with
zero LLM calls.

**Never cut:** frozen `AS_OF` · evidence table · inline verbatims · the PDF · the
second laptop.

---

## 10. Verify before putting on a slide

1. **Android Doze dates** — 6.0 = 2015-10-05, 7.0 = 2016-08-22. From model
   knowledge, *not* the corpus. Load-bearing for the #1 gap. Check them.
2. **Jan-2017 dual spike** — 316 reviews AND ~189 issues, both ~4× baseline.
   Unexplained. Reviews are longer than baseline and 314/316 unique (so not a dedup
   artifact), but know the answer before a judge asks.
3. **`version_id` is a time bucket, not a release** (1,172 of 1,560 are id 110).
   Do NOT claim "ratings dropped after 5.010."
4. **Sentence labels are noisy** — *"Never had a problem so far"* is tagged
   PROBLEM DISCOVERY. Use as corroboration, not gospel. Say so first.
5. **Review collection ends 2017-05-02** — that's the crawl date. Absence of later
   complaints is not resolution.
