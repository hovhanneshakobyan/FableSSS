"""Terminal chat. The ReAct loop is printed as it runs, not hidden.

    .venv/bin/python -m agent                       # interactive
    .venv/bin/python -m agent -q "why do users..."  # one shot, scriptable
    .venv/bin/python -m agent --dry                 # tools only, no LLM, no key

Seeing every tool call and its result is the whole point during development:
when a free-tier model mangles an argument or invents a number, you want that
visible in the transcript rather than smoothed into a confident paragraph.
"""
from __future__ import annotations
import argparse
import json
import sys

from agent.graph import build_agent
from agent.llm import describe_provider, init_llm
from agent.tools import TOOLS, close_kb

C = {"dim": "\033[2m", "b": "\033[1m", "cy": "\033[36m", "gr": "\033[32m",
     "yl": "\033[33m", "rd": "\033[31m", "x": "\033[0m"}
if not sys.stdout.isatty():
    C = dict.fromkeys(C, "")

BANNER = f"""{C['b']}Silent Stakeholder{C['x']} {C['dim']}· ReAct agent over 1,560 reviews / 1,718 issues{C['x']}
{C['dim']}/tools  /reset  /quit   ·  provider: {{prov}}{C['x']}

{C['dim']}try: "what do users complain about that developers filed under a different name?"{C['x']}"""


def _preview(text: str, n: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "…"


def _args_str(args: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}"
                     for k, v in (args or {}).items())


def text_of(msg) -> str:
    """Message text, whatever shape the provider used.

    Groq returns a plain string. Gemini returns a list of parts —
    [{"type": "text", "text": ...}] mixed with thinking blocks — so treating
    content as `str` silently dropped the final answer: the run completed with
    eight tool calls and printed nothing.
    """
    c = msg.content
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        out = []
        for part in c:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                out.append(part.get("text", ""))
        return "\n".join(p for p in out if p).strip()
    return ""


def render(msg) -> None:
    """Print one message from the loop. Tool calls in cyan, results dimmed."""
    kind = getattr(msg, "type", "")
    if kind == "ai":
        for tc in getattr(msg, "tool_calls", None) or []:
            print(f"  {C['cy']}→ {tc['name']}{C['x']}({_args_str(tc.get('args'))})")
        if txt := text_of(msg):
            print(f"\n{C['gr']}{txt}{C['x']}\n")
    elif kind == "tool":
        print(f"  {C['dim']}  {_preview(msg.content)}{C['x']}")


def run_turn(app, text: str, thread: str, trace_path: str | None = None) -> None:
    # ~2 graph steps per tool round, so 60 allows the ~10-call budget in the
    # prompt plus headroom. The prompt is what should stop the loop; this is
    # the backstop for when it doesn't.
    cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 60}
    seen, final = 0, []
    try:
        for state in app.stream({"messages": [("user", text)]}, cfg,
                                stream_mode="values"):
            msgs = state.get("messages", [])
            for m in msgs[seen:]:
                render(m)
            seen = len(msgs)
            final = msgs
    except KeyboardInterrupt:
        print(f"\n{C['yl']}(interrupted){C['x']}\n")
    except Exception as exc:                      # a bad key, a 404, a 429
        blob = f"{type(exc).__name__}: {exc}"
        if any(s in blob for s in ("429", "RESOURCE_EXHAUSTED", "rate_limit",
                                   "413", "Request too large")):
            from agent.llm import RATE_HELP
            # Show which limit actually tripped — per-minute and per-day need
            # different responses (wait vs switch), and hiding the message
            # makes them indistinguishable.
            detail = next((ln for ln in blob.replace("\\n", "\n").splitlines()
                           if "limit" in ln.lower() or "TPM" in ln or "TPD" in ln),
                          blob)
            print(f"\n{C['rd']}Rate limited on {describe_provider()}.{C['x']}\n"
                  f"  {_preview(detail, 220)}\n{C['dim']}{RATE_HELP}{C['x']}\n")
        elif "404" in blob or "not_found" in blob.lower():
            print(f"\n{C['rd']}Model not available to this key.{C['x']} "
                  f"{_preview(blob, 200)}\n{C['dim']}Google retires models for "
                  f"NEW keys while still listing them. Set SS_MODEL to a current "
                  f"one.{C['x']}\n")
        else:
            print(f"\n{C['rd']}LLM/tool error:{C['x']} {blob}\n"
                  f"{C['dim']}Check the key for {describe_provider()}.{C['x']}\n")
    if trace_path and final:
        from agent import trace
        trace.write(final, text, describe_provider(), trace_path)
        s = trace.summarise(final)
        print(f"{C['dim']}trace -> {trace_path}  "
              f"({s['tool_calls']} calls: {s['qdrant_calls']} qdrant / "
              f"{s['lexical_calls']} raw){C['x']}\n")


def dry_run() -> int:
    """Exercise the tool belt with no LLM at all — proves the KB layer works."""
    from agent import tools as T
    print(f"{C['b']}tools{C['x']}  {len(TOOLS)}: "
          f"{', '.join(t.name for t in TOOLS)}\n")
    for label, call in (
            ("polarity(battery,drain,overheat)",
             lambda: T.polarity.invoke({"terms": "battery,drain,overheat"})),
            ("polarity(doze,wakelock,jobscheduler)",
             lambda: T.polarity.invoke({"terms": "doze,wakelock,jobscheduler"})),
            ("control(battery,drain,overheat)",
             lambda: T.control.invoke({"terms": "battery,drain,overheat"})),
            ("count_terms(syncing disabled)",
             lambda: T.count_terms.invoke({"terms": "syncing disabled"})),
            ("get_issue(857)", lambda: T.get_issue.invoke({"number": 857})),
    ):
        print(f"{C['cy']}{label}{C['x']}\n  {_preview(call(), 400)}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent", description=__doc__.split("\n")[0])
    ap.add_argument("-q", "--ask", help="single question, then exit")
    ap.add_argument("--dry", action="store_true", help="tools only, no LLM")
    ap.add_argument("--provider", help="groq|gemini|ollama (default: autodetect)")
    ap.add_argument("--model", help="override the model id")
    ap.add_argument("--trace", metavar="PATH",
                    help="write the FULL untruncated transcript to a .md file")
    a = ap.parse_args(argv)

    if a.dry:
        try:
            return dry_run()
        finally:
            close_kb()

    llm = init_llm(a.provider, a.model)           # SystemExits with setup help
    app = build_agent(model=llm)
    thread = "main"

    try:
        if a.ask:
            run_turn(app, a.ask, thread, a.trace)
            return 0

        print(BANNER.format(prov=describe_provider()))
        while True:
            try:
                text = input(f"{C['b']}you ›{C['x']} ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not text:
                continue
            if text in ("/quit", "/q", "/exit"):
                return 0
            if text == "/tools":
                for t in TOOLS:
                    print(f"  {C['cy']}{t.name:<22}{C['x']}"
                          f"{_preview(t.description, 96)}")
                continue
            if text == "/reset":
                thread = f"t{id(object())}"       # new thread = fresh history
                print(f"{C['dim']}history cleared{C['x']}")
                continue
            run_turn(app, text, thread, a.trace)
    finally:
        close_kb()


if __name__ == "__main__":
    sys.exit(main())
