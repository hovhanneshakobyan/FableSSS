"""LangGraph ReAct agent over the Silent Stakeholder knowledge base.

    .venv/bin/python -m agent            # terminal chat

The agent reasons; `kb` computes. Every number in an answer comes from a tool
result, never from the model — see agent/prompt.py for how that is enforced.
"""
from agent.graph import build_agent
from agent.llm import init_llm, describe_provider
from agent.tools import TOOLS, close_kb

__all__ = ["build_agent", "init_llm", "describe_provider", "TOOLS", "close_kb"]
