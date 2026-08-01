"""Full-fidelity run transcripts.

The terminal renderer truncates every tool result to 150 chars so the loop stays
readable while it runs. That is the right default to watch, and the wrong thing
to audit: reviewing a run against the truncated view once produced a false
accusation of fabricated citations, because the cited ids were in the 90% of
the payload that never reached the screen.

So: one writer, no truncation anywhere, and a Qdrant/raw attribution per call
so a reader can tell which numbers are measurements and which are retrieval.
"""
from __future__ import annotations
import datetime
import json

# Which tools open the Qdrant client — see kb/search.py. The lexical tools scan
# data/raw/*.json and never touch it, which is why counts stay reproducible by
# hand with grep.
ENGINE = {"top_gaps", "why_gap", "missed_gap"}

SEMANTIC = {"search_reviews", "search_issues", "compare_vocabularies",
            "related_issues"}


def _text(msg) -> str:
    from agent.cli import text_of
    return text_of(msg)


def summarise(messages) -> dict:
    calls = [tc["name"] for m in messages
             for tc in (getattr(m, "tool_calls", None) or [])]
    return {"tool_calls": len(calls),
            "qdrant_calls": sum(1 for c in calls if c in SEMANTIC),
            "lexical_calls": sum(1 for c in calls if c not in SEMANTIC),
            "tools_used": sorted(set(calls))}


def to_markdown(messages, question: str, provider: str) -> str:
    s = summarise(messages)
    out = [
        "# Silent Stakeholder — run transcript", "",
        f"- **Question:** {question}",
        f"- **Model:** `{provider}`",
        f"- **When:** {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- **Tool calls:** {s['tool_calls']} "
        f"({s['qdrant_calls']} Qdrant / {s['lexical_calls']} raw-JSON)", "",
        "> Qdrant calls *discover* (semantic). Raw-JSON calls *prove* "
        "(exact word-boundary counts, reproducible with grep). Every number "
        "below comes from a raw-JSON call.", "",
        "---", "",
    ]

    pending: dict[str, dict] = {}
    step = 0
    for m in messages:
        kind = getattr(m, "type", "")
        if kind == "human":
            continue
        if kind == "ai":
            for tc in getattr(m, "tool_calls", None) or []:
                step += 1
                pending[tc["id"]] = {"step": step, "name": tc["name"],
                                     "args": tc.get("args", {})}
            if txt := _text(m):
                out += ["## Final answer", "", txt, ""]
        elif kind == "tool":
            info = pending.get(getattr(m, "tool_call_id", ""), {})
            name = info.get("name", getattr(m, "name", "?"))
            tag = "QDRANT" if name in SEMANTIC else "raw JSON"
            args = json.dumps(info.get("args", {}), ensure_ascii=False)
            out += [f"### {info.get('step', '?')}. `{name}` — {tag}", "",
                    f"**Arguments:** `{args}`", "", "**Full result:**", "",
                    "```json", _pretty(str(m.content)), "```", ""]
    return "\n".join(out)


def _pretty(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return raw


def write(messages, question: str, provider: str, path: str) -> str:
    md = to_markdown(messages, question, provider)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    return path
