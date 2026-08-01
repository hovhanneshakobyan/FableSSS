"""Chat UI for the Silent Stakeholder agent.

    make ui          # .venv/bin/streamlit run ui/app.py

Same agent as `make chat`, same tools, same prompt — only the surface differs.
Tool calls are shown UNTRUNCATED here, which the terminal cannot do: reviewing a
run against a truncated view once produced a false accusation of fabricated
citations, because the cited ids sat in the part that never reached the screen.

Streamlit re-executes this file top to bottom on every interaction. Two things
follow, and both are load-bearing:

  * The agent is built inside @st.cache_resource. Without it, every keystroke
    would construct a new KB, and Qdrant local mode refuses a second client on
    the same folder ("Storage folder ... already accessed by another instance").
  * Conversation state lives in st.session_state, not in local variables.
    LangGraph's checkpointer keys history off thread_id, so the same thread_id
    across reruns is what makes the conversation multi-turn.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.graph import build_agent          # noqa: E402
from agent.llm import DEFAULTS, RATE_HELP, detect_provider, init_llm  # noqa: E402
from agent.trace import ENGINE, SEMANTIC     # noqa: E402

st.set_page_config(page_title="Silent Stakeholder", page_icon="🔍", layout="wide")

# The four graded questions first — the brief is scored on the ranked findings,
# the confidence calibration, the evidence trace and the verdicts — then the
# three live-defense challenges a judge actually asks, then free exploration.
SUGGESTIONS = [
    "What are the top unmet needs the roadmap is missing? Rank them.",
    "Defend the confidence score on gap #1 — why that number and not 90?",
    "Why is #1 ranked above #2? Compare their evidence.",
    "Here's a gap you missed: dark mode. Why isn't it in your output?",
    "Show me the evidence trace for the top gap — by id.",
    "Is battery drain a real unmet need, or a platform artefact?",
    "Which gaps are MISUNDERSTOOD versus simply IGNORED, and how do you tell?",
    "What did users ask for that never became a GitHub issue at all?",
]


@st.cache_resource(show_spinner=False)
def get_agent(provider: str, model: str):
    """One agent per (provider, model). Cached across reruns — see module docs."""
    return build_agent(model=init_llm(provider, model or None))


@st.cache_data(show_spinner=False)
def get_findings() -> dict | None:
    """The engine's ranked gaps. Plain JSON off disk — no Qdrant, no LLM.

    This is the graded deliverable, so it renders even if every API key is
    missing and the chat half of the app is dead: the findings do not depend
    on a provider being reachable.
    """
    from gaps import engine
    return engine.load()


VERDICT_COLOR = {"IGNORED": "🔴", "UNDER-PRIORITIZED": "🟠",
                 "MISUNDERSTOOD": "🟣"}


def render_gap(g: dict) -> None:
    """One finding, with all four things the brief demands, in rank order."""
    m, s = g["metrics"], g["score"]
    st.markdown(f"### {VERDICT_COLOR.get(g['verdict'], '⚪')} #{g['rank']} · "
                f"{g['need']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Confidence", f"{g['confidence']}%")
    c2.metric("Verdict", g["verdict"])
    c3.metric("User signal", f"{m['n_reviews']} reviews",
              f"{m['star_deficit']}★ vs 3.43")

    st.caption(f"**Users say** `{'`, `'.join(g['symptom_terms'])}`  ·  "
               f"**Backlog says** "
               f"`{'`, `'.join(g['mechanism_terms']) if g['mechanism_terms'] else '—'}`")
    st.markdown(f"**Verdict basis** — {g['reason']}")

    with st.expander(f"Why {g['confidence']}%? — full arithmetic, "
                     "every component and penalty"):
        st.code(s["formula"], language="text")
        a, b = st.columns(2)
        a.caption("**E — is the signal really there?**")
        a.json(s["E"], expanded=True)
        b.caption("**L — is the roadmap really missing it?**")
        b.json(s["L"], expanded=True)
        if s["penalties"]:
            st.caption("**Penalties** — what this finding lost, and why")
            for p in s["penalties"]:
                st.markdown(f"- **−{p['cost']} {p['code']}** — {p['why']}")
        else:
            st.caption("No penalties applied.")
        st.caption(f"Verdict counts: `{g['why']}`")
        st.caption(f"Negative control (AntennaPod): {m['control_ratio']}× — "
                   f"{m['control_reading']}")

    with st.expander(f"Evidence trace — {len(g['evidence']['reviews'])} reviews, "
                     f"{len(g['evidence']['issues'])} issues, "
                     f"{m['bridge_n']} bridge documents (every claim by id)"):
        st.caption("**User signals** — latent families in bold are why this is "
                   "not just a complaint count")
        for r in g["evidence"]["reviews"]:
            fam = f" · **{'/'.join(r['families'])}**" if r["families"] else ""
            st.markdown(f"`{r['cite']}` {r['star']}★ {r['date']}{fam}  \n"
                        f"> {r['text']}")
        st.caption("**Roadmap response**")
        for i in g["evidence"]["issues"]:
            st.markdown(f"`{i['cite']}` {i['state']} · {i['days_open']}d open · "
                        f"{i['type'] or 'no type'} · "
                        f"{i['milestone'] or 'no milestone'} — {i['title']}")
        if g["evidence"]["bridge"]:
            st.caption("**Bridge documents** — one author used BOTH "
                       "vocabularies, so the mapping is observed, not assumed")
            for b in g["evidence"]["bridge"]:
                st.markdown(f"`{b['cite']}` — '{b['symptom']}' + "
                            f"'{b['mechanism']}'")


def render_findings() -> None:
    res = get_findings()
    if not res:
        st.warning("No findings yet. Run `make gaps` to build "
                   "`data/gaps.json`, then reload.")
        return

    meta = res["meta"]
    st.caption(f"{meta['candidates_considered']} candidates considered · "
               f"{meta['surfaced']} surfaced · {meta['reviews']} reviews vs "
               f"{meta['issues']} issues · frozen as of {meta['as_of']}")
    for g in res["gaps"]:
        render_gap(g)
        st.divider()

    with st.expander(f"Considered and REJECTED — all {len(res['rejected'])} "
                     "candidates, with the component that failed"):
        st.caption("This is the answer to \"here's a gap you missed\". "
                   "A candidate is either here with a reason, or it was never "
                   "considered — and saying so plainly beats improvising.")
        st.dataframe(
            [{"candidate": r["label"], "route": r["route"],
              "failed": r["failed"], "confidence": r.get("confidence"),
              "detail": r["detail"]} for r in res["rejected"]],
            use_container_width=True, hide_index=True)


def render_tool_call(call: dict) -> None:
    """One tool call: what was asked, and the complete answer it got."""
    tag = ("🎯 engine" if call["name"] in ENGINE else
           "🔎 Qdrant" if call["name"] in SEMANTIC else "📐 raw JSON")
    args = ", ".join(f"{k}={v!r}" for k, v in (call.get("args") or {}).items())
    with st.expander(f"{tag} · `{call['name']}({args})`", expanded=False):
        try:
            st.json(json.loads(call["result"]), expanded=False)
        except (ValueError, TypeError):
            st.code(call["result"])


def render_turn(turn: dict) -> None:
    with st.chat_message(turn["role"]):
        if turn["role"] == "assistant" and turn.get("tools"):
            n_q = sum(1 for c in turn["tools"] if c["name"] in SEMANTIC)
            st.caption(f"{len(turn['tools'])} tool calls · "
                       f"{n_q} Qdrant (discover) / "
                       f"{len(turn['tools']) - n_q} raw JSON (prove)")
            for call in turn["tools"]:
                render_tool_call(call)
        if turn.get("text"):
            st.markdown(turn["text"])


def run(agent, question: str) -> dict:
    """Stream one turn, rendering tool calls as they land."""
    from agent.cli import text_of

    cfg = {"configurable": {"thread_id": st.session_state.thread},
           "recursion_limit": 60}
    calls: dict[str, dict] = {}
    order: list[str] = []
    answer = ""
    seen = 0
    slot = st.empty()

    for state in agent.stream({"messages": [("user", question)]}, cfg,
                              stream_mode="values"):
        msgs = state.get("messages", [])
        for m in msgs[seen:]:
            kind = getattr(m, "type", "")
            if kind == "ai":
                for tc in getattr(m, "tool_calls", None) or []:
                    calls[tc["id"]] = {"name": tc["name"], "args": tc.get("args"),
                                       "result": ""}
                    order.append(tc["id"])
                if txt := text_of(m):
                    answer = txt
            elif kind == "tool":
                cid = getattr(m, "tool_call_id", "")
                if cid in calls:
                    calls[cid]["result"] = str(m.content)
        seen = len(msgs)
        slot.caption(f"⏳ {len(order)} tool calls…" if not answer else "")

    slot.empty()
    return {"role": "assistant", "text": answer,
            "tools": [calls[c] for c in order]}


# ------------------------------------------------------------------ sidebar
detected = detect_provider()
with st.sidebar:
    st.subheader("Silent Stakeholder")
    st.caption("1,560 K-9 Mail reviews · 1,718 GitHub issues · 2015–2017")

    provider = st.selectbox(
        "Provider", ["groq", "gemini", "ollama"],
        index=["groq", "gemini", "ollama"].index(detected) if detected else 0,
        help="Quota is per model — switching model gets a fresh allowance.")
    model = st.text_input("Model", value=DEFAULTS.get(provider, ""),
                          help="Leave as-is unless a model 404s or is capped.")

    if st.button("New conversation", use_container_width=True):
        st.session_state.thread = f"ui-{uuid.uuid4().hex[:8]}"
        st.session_state.log = []
        st.rerun()

    st.divider()
    st.caption(
        "**Qdrant tools discover** — semantic search, never a number on a slide.\n\n"
        "**raw-JSON tools prove** — exact word-boundary counts, reproducible "
        "with `grep`.\n\nEvery count shows its denominator.")
    if not detected:
        st.warning("No API key found. `source env.sh` before launching, "
                   "or run Ollama locally.")

# --------------------------------------------------------------------- main
st.session_state.setdefault("thread", f"ui-{uuid.uuid4().hex[:8]}")
st.session_state.setdefault("log", [])

# Findings first: it is the graded deliverable and it renders with no API key.
# Chat is the live-defense surface on top of the same numbers.
tab_gaps, tab_chat = st.tabs(["🎯 Findings", "💬 Interrogate"])

with tab_gaps:
    render_findings()

with tab_chat:
    for turn in st.session_state.log:
        render_turn(turn)

    if not st.session_state.log:
        st.markdown("#### Ask the corpus anything")
        st.caption("The first four are the graded questions; the rest are what "
                   "a judge asks next.")
        cols = st.columns(2)
        for i, s in enumerate(SUGGESTIONS):
            if cols[i % 2].button(s, use_container_width=True, key=f"sug{i}"):
                st.session_state.pending = s
                st.rerun()

question = st.chat_input("Ask about K-9 Mail users, issues, or gaps…")
if pending := st.session_state.pop("pending", None):
    question = pending

if question:
    # Rendered inside the chat tab, or the answer would land under the
    # findings list instead of under the question that produced it.
    with tab_chat:
        st.session_state.log.append({"role": "user", "text": question})
        render_turn(st.session_state.log[-1])

        with st.chat_message("assistant"):
            try:
                agent = get_agent(provider, model)
                turn = run(agent, question)
            except Exception as exc:                # rate limit, bad key, 404
                blob = f"{type(exc).__name__}: {exc}"
                if any(s in blob for s in ("429", "RESOURCE_EXHAUSTED",
                                           "rate_limit", "413")):
                    st.error("Rate limited — free tiers are the binding "
                             "constraint. The Findings tab still works: it "
                             "reads the engine's JSON, not the LLM.")
                    st.code(RATE_HELP)
                else:
                    st.error(blob[:600])
                st.stop()

            if turn["tools"]:
                n_q = sum(1 for c in turn["tools"] if c["name"] in SEMANTIC)
                st.caption(f"{len(turn['tools'])} tool calls · {n_q} Qdrant "
                           f"(discover) / {len(turn['tools']) - n_q} "
                           "raw JSON (prove)")
                for call in turn["tools"]:
                    render_tool_call(call)
            if turn["text"]:
                st.markdown(turn["text"])

        st.session_state.log.append(turn)
