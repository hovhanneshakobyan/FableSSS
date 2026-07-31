# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two unrelated things live here

1. **`sealuzh/user_quality`** — a published research dataset (288,065 Google Play reviews for 395 F-Droid apps + 22 code-quality metrics and 8 code-smell categories per APK). Everything tracked in git belongs to it: `csv_files/`, `dbms_dump/`, `code_metrics_scripts/`, `tools/`, `images/`. It is a **frozen artifact** — treat it as read-only input, not as code to maintain.
2. **`silent_stakeholder/`** — the active project, untracked at the repo root. A hackathon build that mines K-9 Mail (`com.fsck.k9`) reviews from that dataset against the app's GitHub backlog to find unmet user needs. All development happens here.

`silent_stakeholder/CLAUDE.md` is the authoritative context for that project and is loaded automatically when working inside it. `PLAN.md` (architecture + verified numbers) and `BUILD.md` (lane assignments, build order) sit alongside it. Read those before writing pipeline code; this file covers only what spans both halves of the repo.

## silent_stakeholder — commands

Run from `silent_stakeholder/`. The venv is Python 3.12; `make` targets that touch Qdrant/fastembed call `.venv/bin/python` explicitly, the rest call bare `python3`.

```bash
./setup.sh                    # create .venv, install requirements.txt
make db                       # create data/gap.db from schema.sql
make ingest                   # data/raw/*.json -> gap.db (asserts 1560/4224/1718)
make control                  # AntennaPod negative control -> data/gap_ap.db
make verify                   # recompute every documented number; exit 1 on drift
.venv/bin/python -m kb build  # embed data/raw -> data/qdrant (~12 min full rebuild)
.venv/bin/python -m kb stats  # docs vs vectors; exit 1 if the index is stale
make chat-dry                 # agent tool belt, no LLM and no API key needed
make chat                     # ReAct chat (needs GROQ_API_KEY / GOOGLE_API_KEY / ollama)
```

`make verify` is the test suite. There is no pytest suite despite the `python3 -m pytest -q` mention in `silent_stakeholder/CLAUDE.md` — add tests under a real path before quoting that command.

Query the corpus (see `kb/README.md` for the full CLI and `--where` grammar):

```bash
.venv/bin/python -m kb search "battery drains overnight" --in k9_reviews --where "star<=2"
.venv/bin/python -m kb lexical battery,drain,overheat --in k9_reviews
.venv/bin/python -m kb polarity battery,drain,overheat --aligned
.venv/bin/python -m kb control battery,drain,overheat     # falsifier vs AntennaPod
```

## silent_stakeholder — architecture

`data/raw/*.json` is the single source of truth (1,560 K-9 reviews, 1,718 K-9 issues, 4,224 labeled sentences, 1,000 AntennaPod issues). Three access layers read it, and knowing which one you are in matters:

| Layer | Reads | Purpose |
|---|---|---|
| `tools.py` | `data/raw/` directly | Pure offline functions (`search_reviews`, `polarity`, `bridge`, `resolution_lag`). Consumed by the pipeline, by Claude Agent SDK tool defs, and verbatim by `mcp_server.py`. |
| `kb/` | `data/raw/` + `data/qdrant/` | The newer, richer layer: `documents.py` (normalize + derive) → `index.py` (embed) → `search.py` (`KB` class), CLI at `python -m kb`. |
| `pipeline/` | `data/raw/` → `data/gap.db` | `a_ingest.py` is the only door into SQLite; `verify.py` audits it. |
| `agent/` | `kb/` only | LangGraph ReAct chat — nine flat tools over `KB`, terminal REPL (`make chat`). Adds no data path. See `agent/README.md`. |

`pipeline/c_embed.py` is the **superseded** embedding path — it builds the same `data/qdrant/` folder from `gap.db` with un-chunked issue bodies. `kb/index.py` replaced it (chunked issues, payload indexes, `--rebuild` guard). Use `kb`; do not run both against the same folder.

`polarity()` exists in both `tools.py` (log2 PII form) and `kb/search.py` (rate-per-1k ratio form). They answer the same question with different scales — do not mix their outputs in one table.

The Makefile also declares `label`, `cluster`, `prove`, `score`, `ui`, `freeze` targets whose files (`pipeline/b_label.py`, `c_cluster.py`, `d_prove.py`, `e_score.py`, `ui/`) **do not exist yet**. `make all` fails past `ingest`. `schema.sql` already has the tables they will fill (`clusters`, `pairs`, `candidates`, `gaps`, `gap_evidence` — currently 0 rows).

## Invariants that break the demo if violated

- **`AS_OF = "2026-07-31"` is frozen** in `kb/documents.py`, `pipeline/a_ingest.py`, and `run_manifest`. Never `datetime.now()` — staleness numbers must not drift between the slide and the stage.
- **No network.** The GitHub API is off-limits; `data/raw/` is already fetched. `tools.py` and `kb/` are pure, offline, sub-100ms.
- **Vectors discover, keywords prove.** Semantic search proposes candidates; every number that reaches a slide comes from the word-boundary regex path (`kb lexical` / `tools.polarity`). An LLM may propose hypotheses and query terms, never assert a count.
- **Every gap needs evidence IDs**, and `review_ids` is the complete set, never a sample — the UI prints `len()` as the headline.
- **Mind the window**: reviews cover 2015-11-29→2017-05-02, issues 2015-03-15→2017-12-31, so 37% of the backlog predates any review. Use `polarity(aligned=True)` / `--aligned` for the defensible ratio.
- Run `make verify` before quoting any figure from `PLAN.md`/`CLAUDE.md` prose.

## Repo hygiene

- `silent_stakeholder/data/raw/` and `silent_stakeholder/data/qdrant/` each contain their **own nested `.git`**. Root-level `git add -A` will not descend into them; commit inside those directories if their contents need versioning.
- The dataset half is legacy and unrunnable as-is: `code_metrics_scripts/` is Python 2.7 (Androguard/Apkil/apktool, needs `src/config.ini` and `apktool.jar`); `tools/` is a Java review crawler (`java -jar extractor.jar extractor=reviews`, needs PhantomJS + `config.properties`). Don't modernize either unless asked.
- Anthropic API notes for this project (thinking on by default for `claude-opus-5`, structured-output schema constraints, prompt-cache rules) are in `silent_stakeholder/CLAUDE.md` and `PLAN.md` §1.
