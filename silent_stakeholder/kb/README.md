# Knowledge base

Two inputs, nothing else:

```
data/raw/*.json  ──▶  kb.documents  ──▶  kb.index  ──▶  data/qdrant/
                            │                              │
                            └──── kb.search (KB) ◀──────────┘
```

No `gap.db`, no SQLite, no network, no LLM. `data/raw/` is the only source of
truth; `data/qdrant/` is a derived cache that can be deleted and rebuilt.

## Corpora

| Corpus | Docs | Points | Point id | Embedded text |
|---|---|---|---|---|
| `k9_reviews` | 1,560 | 1,560 | review uuid | full review |
| `k9_issues` | 1,718 | 2,765 | `number*100 + chunk` | `title + body`, chunked |
| `k9_sentences` | 4,224 | 4,224 | row index (1-based) | sentence |
| `ap_issues` | 1,000 | — | — | **not embedded** — raw-only negative control |

Model `BAAI/bge-small-en-v1.5`, 384-dim, cosine. Qdrant runs in local mode:
a folder, no server, no process to die on stage.

Issues are chunked (900 chars, 150 overlap, 24 max) because a single truncated
vector per issue hid most of the corpus: 46% of bodies run past 600 chars, and
that cut discarded 56% of all body text. Measured on 145 long issues, a phrase
from inside the embedded window found its issue at recall@10 **88%**; a phrase
from just past the cut, **36%**. Chunking now embeds 89% of body text.
Retrieval runs at chunk level and `search` collapses hits back to issues, so
one issue matching in four places is still one hit — with `chunks_matched`
recording how many. Counting still runs over whole documents, so a rate per
1,000 documents never turns into a rate per 1,000 chunks.

`ap_issues` carries no vectors on purpose. The control is used by comparing
term *rates* against K-9 (`kb control`), and a rate comes from keyword
counting — nothing asks a control corpus for its nearest neighbours. It loads
from raw like everything else, so `lexical` and `control` see all 1,000 rows.

Derived payload fields are computed in `kb/documents.py` and nowhere else, so
the vector payload and the keyword count can never disagree:
`ym`, `star_band`, `days_open` (against frozen `AS_OF = 2026-07-31`),
`type_label`, `labels`, `is_needs_info`, `is_not_planned`.

## Two retrieval modes — keep them separate

**Semantic** bridges vocabularies (`battery drain` → `Doze`). It proposes
candidates. It never produces a number that goes on a slide.

**Lexical** is a word-boundary regex over `data/raw/`. Exact, auditable,
reproducible by hand with `grep`. Every count comes from here.

`polarity()` is the thesis metric: term rate per 1k reviews ÷ rate per 1k
issues. `> 1.2` user-led (unmet need), `< 0.83` dev-led (tracked in a
vocabulary users never say).

`control()` is the falsifier: the same terms against the AntennaPod backlog.
A term just as loud in an unrelated Android app is a platform artefact, not a
K-9 gap.

### Mind the window

Reviews cover 2015-11-29 → 2017-05-02. Issues cover 2015-03-15 → 2017-12-31,
so **37% of the backlog was filed when no review data exists**. Comparing the
two full corpora compares different periods. `polarity(aligned=True)` /
`--aligned` restricts issues to the review window and is the defensible
number; it is off by default so published figures don't move silently.
It matters: `battery` reads 1.79x unaligned, **1.46x aligned**.

## CLI

```bash
.venv/bin/python -m kb stats                     # docs vs vectors; exit 1 if stale
.venv/bin/python -m kb eval [--n 150]            # retrieval recall, self-supervised
.venv/bin/python -m kb build [--only C] [--rebuild]

.venv/bin/python -m kb search "battery drains overnight"            # all collections
.venv/bin/python -m kb search "sync is slow" --in k9_issues --where state=open
.venv/bin/python -m kb search "crash" --in k9_reviews --where star<=2 --limit 5

.venv/bin/python -m kb lexical battery,drain,overheat --in k9_reviews
.venv/bin/python -m kb lexical doze --in ap_issues                  # control, raw-only
.venv/bin/python -m kb polarity battery,drain,overheat
.venv/bin/python -m kb control battery,drain,overheat
.venv/bin/python -m kb get k9_issues 857 970
```

`--where` takes `key=value` (comma-separated value = any-of) and
`key<=value` / `key>=value`. Add `--json` to any command for machine output.
The same `where` semantics apply to `search` (Qdrant filter) and `lexical`
(replayed in Python over raw JSON).

## Python

```python
from kb import KB
kb = KB()

kb.search("battery drains overnight", "k9_issues", limit=5)
kb.search_all("cannot delete account")                 # same query, every corpus
kb.neighbors("k9_issues", 857)                         # more-like-this, no re-embed
kb.get("k9_reviews", ["d7f5713f-afca-11e6-be22-b252784303c8"])

kb.lexical(["battery", "drain"], "k9_reviews", where={"star": {"lte": 2}})
kb.polarity(["battery", "drain", "overheat"])           # users vs K-9 backlog
kb.control(["battery", "drain", "overheat"])            # K-9 vs AntennaPod
kb.stats()
```

## Rebuilding

## Measuring it

`kb eval` scores retrieval against answers the corpora already know — every
sentence has exactly one parent review, every body phrase has exactly one
issue. No labelling, no LLM judge, fixed seed, so two runs are comparable.
Run it before and after any change to the model, chunk size, or `BODY_CHARS`.
Current baseline is in the `kb/eval.py` docstring.

## Known limits

- **Issue comments are not in the KB.** 8,399 comment bodies across 1,614
  issues — including all 180 on #857 — exist only as `comments_url` in the raw
  JSON. Adding them needs a GitHub fetch, which this project forbids. Today
  the KB knows what an issue *opened with*, not what it *became*.
- **Dense-only retrieval.** Exact strings (`IMAP IDLE`, a version number, an
  issue number) are served by the raw-scan `lexical` path, not by Qdrant. A
  BM25 sparse vector alongside the dense one would fuse both into one ranking;
  `fastembed`'s `Qdrant/bm25` is available offline and was verified to load.
- **Sentence labels are third-party and coarse** — 73% are `OTHER`/`Other`,
  so `intention`/`topic` filters are weak slicers, not a taxonomy.
- **`type_label` is null on 53% of issues, `milestone` on 85%.** Filters on
  them silently shrink the corpus; say so when quoting a filtered count.
- 24 duplicate review texts and 387 duplicate sentence strings remain, by
  design — they are real repeated user complaints, and deduping would bias any
  rate computed from them. Retrieval already ranks the 250 near-empty
  sentences (`.`, `1.`) below anything meaningful; measured 0/10 in top hits.

## Rebuilding

`build` keeps an existing collection unless `--rebuild` is passed — a
half-finished re-embed on stage is worse than a stale one. A full rebuild of
all three collections is ~12 min of CPU. Row counts are asserted at load
time: a silently truncated raw file fails loudly instead of shipping a
smaller index.
