# agent — ReAct chat over the knowledge base

```
you ask ──▶ LLM ──▶ tool call ──▶ kb ──▶ result ──▶ LLM ──▶ answer + citations
             ▲                                        │
             └────────────── loop ────────────────────┘
```

A LangGraph `create_react_agent` with nine tools wrapping `kb`, an in-process
checkpointer for multi-turn history, and a terminal REPL that prints every tool
call as it happens. No new data path: `kb` stays the only door to the corpus.

## Run

```bash
make chat-dry                 # tool belt only — no LLM, no key, proves kb works
make chat                     # interactive
.venv/bin/python -m agent -q "why do users say sync is broken?"
```

`/tools` lists the belt, `/reset` clears history, `/quit` exits.

## Provider

Free tiers only, auto-detected in this order — set one and re-run:

| Provider | Key | Notes |
|---|---|---|
| Groq | `GROQ_API_KEY` — [console.groq.com/keys](https://console.groq.com/keys) | fastest, solid tool calling |
| Gemini | `GOOGLE_API_KEY` — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | big context |
| Ollama | none — `brew install ollama && ollama pull qwen2.5:7b` | fully offline, weaker at multi-hop |

Override with `SS_PROVIDER=groq|gemini|ollama` and `SS_MODEL=<id>`. Model ids
move faster than `llm.py` does; if a default 404s, set `SS_MODEL` rather than
editing the defaults.

## The tool belt

Split along the project's central line — **vectors discover, keywords prove**:

| Tool | Path | Use |
|---|---|---|
| `search_reviews` `search_issues` | Qdrant | find by meaning; never a count |
| `compare_vocabularies` | Qdrant | one query, all three corpora — the misframing detector |
| `related_issues` | Qdrant | more-like-this from an issue number |
| `count_terms` | raw JSON | exact word-boundary count — **evidence** |
| `polarity` | raw JSON | user rate ÷ backlog rate, always aligned |
| `control` | raw JSON | same terms vs AntennaPod — the falsifier |
| `get_issue` `get_review` | raw JSON | full document behind a citation |

Schemas are flat scalars and comma-separated term strings on purpose: a 7B
model reliably mangles nested arguments, and a malformed `where` clause fails
as a wrong answer rather than an error. Every count returns its denominator.

The lexical tools scan raw JSON and never touch Qdrant, so `make chat-dry`
works even while a `kb build` holds the local-mode lock.

## What the prompt enforces

`prompt.py` carries the hunt recipe, because a bare ReAct loop asked to "find
problems" runs one search and summarises the top hits — which surfaces exactly
the obvious complaints. The recipe is: `compare_vocabularies` → split the
symptom and mechanism word sets → `polarity` on both → `control` to falsify →
`get_issue` for the backlog response. A real gap is a **pair**: symptoms
user-led (>1.2), mechanism dev-led (<0.83).

It also enforces the project rule — **the model proposes, the tools compute**.
No number may appear in an answer that did not come out of a tool result.

## Status

Verified end to end on Groq / `llama-3.3-70b-versatile`: the loop, all nine
tools against the live index, multi-turn memory, and the CLI renderer. On the
hunt question the model ran the full recipe unprompted — `compare_vocabularies`
→ symptom/mechanism `polarity` pair → `control` → `get_issue` → `get_review` —
and every number in its answer traced back to a tool result.

Also verified on Gemini `gemini-3.6-flash`, which ran the recipe cleanly:
`compare_vocabularies` → `polarity(battery,drain)` 1.46 user-led →
`polarity(doze,wakelock,idle)` 0.23 dev-led → `control` 1.75 k9-specific →
`get_issue(857)` → `get_review`. That is the canonical finding, unprompted.

### Free-tier quota is the binding constraint

Measured 2026-07-31. This decides how much you can iterate, so budget for it:

| Provider | Model | Limit | Practical effect |
|---|---|---|---|
| Groq | `llama-3.3-70b-versatile` | 12k tokens/**min**, 100k/day | ~2 requests/min — a 6-call run needs ~3 min |
| Gemini | `gemini-3.6-flash` | 20 requests/**day** | ~2 runs, then done for the day |
| Gemini | `*-flash-lite` | separate bucket per model | the escape hatch when one is capped |
| Ollama | any | none | unlimited |

**Quota is per model, not per key.** `GenerateRequestsPerDayPerProjectPerModel`
means switching `SS_MODEL` gets a fresh allowance — verified: with
`gemini-3.6-flash` capped, `gemini-3.5-flash-lite` completed a full run.

The per-minute ceiling is the one that bites during development: an agent run
bursts ~6 calls of ~5k tokens, which spends three minutes of Groq's allowance
in seconds. Groq's `x-ratelimit-*` response headers report the per-MINUTE
buckets only — a small request succeeding there says nothing about the daily
budget.

Groq is the better daily budget; Gemini gave the better analysis. Both keys can
sit in `env.sh` — detection prefers Groq, so use `SS_PROVIDER=gemini` to switch.
A per-minute limit now retries itself (`max_retries=4`); a per-day cap cannot,
and the CLI prints the switch options instead of a stack trace.

**Google retires models for new keys while still listing them.** A fresh key
gets `404 no longer available to new users` on `gemini-2.5-flash` and a
misleading `429 ... limit: 0` on `gemini-2.0-flash`. Probe with
`curl .../v1beta/models?key=$GEMINI_API_KEY` before believing the model list.

### Bugs found by running it, all fixed

- **Qdrant lock race.** LangGraph's ToolNode runs a turn's tool calls in
  parallel threads; `KB.qc` lazy-inits without a lock, so two threads opened two
  local-mode clients and the second died with "Storage folder … already accessed
  by another instance". Reproduced 3/4 failures on four parallel calls; now
  8/8 and 6/6 on mixed loads. `kb/` is untouched — the lock lives in `tools.py`.
- **Silent phrase miscount.** The model passed `"battery drain"` as one
  multi-word term. That matches the adjacent phrase (5 of 1,560) instead of
  either word (44 of 1,560), flipping polarity from 1.46 user-led to 0.87 — a
  confidently wrong answer with no error anywhere. Phrases are legitimate
  (`"syncing disabled"` is a real 26-review signal), so the fix is `_note()`:
  any multi-word term comes back with the comma-separated alternative attached.
- **Schema type rejection.** The model emitted `{"max_star": "2"}` — a string
  where the schema said integer. Groq validates tool calls server-side, so it
  400s before any of our code runs and the turn dies. Every numeric parameter
  is now typed `int | str` (schema: `anyOf[integer,string]`) and squeezed back
  through `_int()`; junk falls back to the default rather than raising.
- **Token budget blowout.** Three parallel `compare_vocabularies(limit=10)`
  calls exceeded Groq's 12k tokens/minute — tool results persist in the
  transcript, so they are re-billed on every later turn. Fixed on both sides:
  `_cap()` clamps model-supplied limits, `SNIP` dropped 240→150 chars, and a
  `pre_model_hook` trims the model's input window to ~5k tokens while the
  checkpointer keeps full history. Measured 12.8k→4.3k tokens, no orphaned
  ToolMessages (`start_on="human"`).
- **Null ratio read as a finding.** `polarity("syncing issues")` matched 0/1560
  and 0/1086; `kb` labels a null ratio `"balanced"`, and the model reported
  that developers mention syncing more than users. `_empty()` now overrides the
  label with `NO DATA` / `ONE SIDE EMPTY`.
- **Citations did not round-trip.** The prompt tells the model to cite
  `rev:83c34e81` / `k9#857`, so it fed those handles straight back into
  `get_review` / `get_issue` — which wanted the bare id and returned an error.
  Observed burning two tool calls before the model guessed. `_bare()` now
  strips `rev:` / `sent:` / `k9#` / `#` on every lookup.
- **Never terminating.** Gemini explored to the 40-step recursion limit without
  concluding. The prompt now carries an explicit ~10-call budget and a stop
  condition; the limit is a 60-step backstop, not the control.

Next, in order:
1. **The model still under-weights its own falsifier.** On the run above it
   reported `control` = 1.43 ("platform-wide" — below the 1.5 bar) and then
   concluded a misframing gap anyway. Tighten the prompt so a failed control
   forces a downgrade, and consider returning a blunt `verdict` field from
   `control()` rather than a ratio the model has to interpret.
2. Add a validation node that rejects an answer containing a digit absent from
   every tool result in the thread. That makes the "no invented numbers" rule
   mechanical instead of a request.
3. If a weaker model shortcuts the recipe: add a deterministic `hunt` node that
   runs the polarity sweep in code and hands scored candidates to the model to
   *name and explain*. Slots in as a graph node; the CLI does not change.
4. Swap `InMemorySaver` for `SqliteSaver` if sessions need to survive restarts.
