# Silent Stakeholder — agent context

**Read this before touching anything. Do NOT re-explore the repo; everything you need is here.**

## What this is
Finds latent unmet user needs by comparing K-9 Mail's user reviews against its GitHub
roadmap from the same period. Hackathon demo: 11:40–12:00.

## Thesis (do not re-derive)
On a mature backlog, gaps are NOT absence — topic subtraction returns ~nothing.
Gaps are **misframing**: same defect, incompatible vocabularies.
Verified: `battery` 53 rev/30 iss (1.95x user) vs `IMAP idle` 2 rev/22 iss (0.10x dev).

## Data — already fetched, in `data/raw/`. NEVER call the GitHub API.
| File | Contents |
|---|---|
| `k9_reviews.json` | 1,560 reviews, 2015-11-29→2017-05-02, keys: id,text,date,star,chars |
| `k9_issues_all.json` | 1,718 issues, 2015-03-15→2017-12-31, raw GitHub JSON |
| `k9_sentences.json` | 4,224 labeled sentences, keys: review_id,text,intention,topic |
| `ap_issues.json` | AntennaPod issues — negative control only |

Stars: 1★277 2★205 3★223 4★282 5★573, mean 3.43.
Issues: 1,552 closed / 166 open. 259 milestone-tagged.
Sentence intentions: PROBLEM DISCOVERY 508, FEATURE REQUEST 209, INFO GIVING 361.

## Key facts (verified — cite these, don't recompute)
- `type: enhancement` median **970 days** to close, 136/386 still open.
  `type: bug` median **195 days**, 21/365 still open. This label IS the priority signal.
- Issue **#857 "Figure out how to deal with Doze (Android 6+)"**: opened 2015-10-23,
  closed 2021-06-30 = **2,077 days (5.7 yrs)**, 180 comments, milestone
  `Mail synchronization`, label `type: enhancement`. This is gap #1's core evidence.
- #970 3.2 yrs. Android 6 Doze shipped 2015-10-05; Nougat 2016-08-22.
- DiD around Nougat = **+0.02** → make NO trend claim. Argue level, not trend.

## Architecture
```
data/raw/*.json -> a_ingest -> gap.db -> c_cluster -> d_prove -> e_score -> ui
```
SQLite (`data/gap.db`), schema in `schema.sql`. No vector DB — embeddings are for
DISCOVERY only; keyword polarity is the PROOF shown on stage.

## Rules
- LLM proposes hypotheses; **code computes every number**. Never let a model assert a count.
- Every gap needs evidence IDs. No evidence, no gap.
- `claude-opus-5`: thinking is ON by default (don't pass `thinking`);
  `temperature`/`top_p`/`budget_tokens` -> 400; no assistant prefill;
  schemas need `additionalProperties:false` + full `required`.
- Cost control: Haiku 4.5 for bulk labeling, Opus 5 only for mechanism + critic.

## File ownership — do not edit outside your lane
| Lane | Files |
|---|---|
| A data | `pipeline/a_ingest.py`, `schema.sql` |
| B cluster | `pipeline/c_cluster.py` |
| C llm | `pipeline/b_label.py`, `pipeline/f_critic.py`, `prompts/` |
| D ui | `ui/**` |
| E score | `pipeline/d_prove.py`, `pipeline/e_score.py` |
| shared | `tools.py` (read-only for everyone but A) |

## Commands
`make db ingest cluster prove score` · `make ui` · `python3 -m pytest -q`
