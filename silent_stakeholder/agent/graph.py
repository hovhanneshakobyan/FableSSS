"""The graph. Deliberately the prebuilt ReAct loop plus one hook.

The POC's value is in the tool belt and the prompt, not in graph topology —
so this stays swappable. When the scripted hunt lands (a deterministic node
that runs the polarity sweep and hands candidates to the model to name), it
slots in as a node here and the CLI does not change.

Memory is an in-process checkpointer keyed by thread_id: multi-turn chat that
survives the session and nothing longer. Swap in SqliteSaver for persistence.
"""
from __future__ import annotations

from langchain_core.messages import trim_messages
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from agent.llm import init_llm
from agent.prompt import SYSTEM
from agent.tools import TOOLS

# Groq's free tier allows 12,000 tokens per MINUTE, and a ReAct transcript only
# grows: every tool result the model has ever seen is re-sent on the next call.
# A three-tool turn over a few rounds crosses it and the run dies with a 413.
# Trimming caps what the model is shown without touching what is stored, so the
# checkpointer keeps the full history for the UI while the LLM sees a window.
MAX_INPUT_TOKENS = 5000


def _approx_tokens(messages) -> int:
    """~4 chars per token, plus per-message overhead for role and tool_call
    envelopes. Deliberately crude: an exact tokenizer would be another
    dependency to buy a number that only feeds a safety margin."""
    total = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        total += len(content) // 4 + 20
        for tc in getattr(m, "tool_calls", None) or []:
            total += len(str(tc.get("args", ""))) // 4 + 10
    return total


def _trim(state: dict) -> dict:
    """Show the model a recent window. `start_on="human"` is what keeps a
    ToolMessage from being orphaned from the AIMessage that requested it —
    an orphan is a 400 from every provider."""
    kept = trim_messages(
        state["messages"], max_tokens=MAX_INPUT_TOKENS,
        token_counter=_approx_tokens, strategy="last",
        start_on="human", include_system=False, allow_partial=False)
    # Never hand back an empty list: one oversized turn would erase the question.
    return {"llm_input_messages": kept or state["messages"][-1:]}


def build_agent(model=None, tools=None, checkpointer=None, trim=True):
    return create_react_agent(
        model=model or init_llm(),
        tools=tools if tools is not None else TOOLS,
        prompt=SYSTEM,
        pre_model_hook=_trim if trim else None,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )
