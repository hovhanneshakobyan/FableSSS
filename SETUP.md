# Setup — Silent Stakeholder agent

This branch (`silent-stakeholder-agent`) is **code only**. The corpora live on
this repo's `main` branch, and the 288k-review research dataset this project was
extracted from lives in a third repo. Nothing here works until the data is in
place, so do this first.

## 1. Code

```bash
git clone -b silent-stakeholder-agent git@github.com:hovhanneshakobyan/FableSSS.git ss
cd ss/silent_stakeholder
```

## 2. Data — from this repo's `main` branch

`main` is laid out as the Qdrant folder itself, with the raw JSON alongside it.
Two directories have to land in specific places:

| From `main` | Goes to |
|---|---|
| `collection/`, `meta.json`, `.lock` | `silent_stakeholder/data/qdrant/` |
| `data/raw/*.json` | `silent_stakeholder/data/raw/` |

```bash
# from inside silent_stakeholder/
git clone -b main git@github.com:hovhanneshakobyan/FableSSS.git /tmp/ss-data
mkdir -p data
cp -R /tmp/ss-data/data/raw data/raw          # 4 JSON files, ~14MB
mkdir -p data/qdrant
cp -R /tmp/ss-data/collection /tmp/ss-data/meta.json data/qdrant/   # ~55MB
```

`data/` is gitignored here on purpose — it is a separate repo with its own
history, and committing it would record broken submodule links.

## 3. Environment

```bash
./setup.sh                      # creates .venv, installs requirements.txt
```

## 4. A free LLM key

`env.sh` is gitignored — **never commit it.** Create your own:

```bash
cat > env.sh <<'EOF'
export GROQ_API_KEY=gsk_...          # console.groq.com/keys
# export GEMINI_API_KEY=...          # aistudio.google.com/apikey
EOF
source env.sh
```

Free-tier limits are the real constraint, measured 2026-07-31:

| Provider | Model | Limit |
|---|---|---|
| Groq | `llama-3.3-70b-versatile` | 12k tokens/**min**, 100k/day |
| Gemini | `gemini-3.6-flash` | **20 requests/day** |
| Gemini | `gemini-3.5-flash-lite` | separate bucket per model |

Quota is **per model**, so `SS_MODEL=<other model>` gets a fresh allowance.
Detection prefers Groq; use `SS_PROVIDER=gemini` to switch. If you want no
ceiling at all: `brew install ollama && ollama pull qwen2.5:7b`.

## 5. Check it works

```bash
make chat-dry                   # tool belt only — no LLM, no key required
.venv/bin/python -m kb stats    # must report 1560 / 2765 / 4224 vectors in sync
make verify                     # only after `make db ingest` — audits every documented number
source env.sh && make chat      # the agent
```

`make chat-dry` is the fastest way to confirm the data landed correctly: it
exercises all nine tools against raw JSON without needing a key. If `kb stats`
says `STALE`, rebuild with `.venv/bin/python -m kb build --rebuild` (~12 min).

## Where to read next

- `silent_stakeholder/agent/README.md` — the agent, its tool belt, and the list
  of bugs already found and fixed by running it
- `silent_stakeholder/run-trace.md` — a real captured run, full untruncated
- `silent_stakeholder/kb/README.md` — the knowledge base and its known limits
- `CLAUDE.md` — how the three data-access layers relate
