"""
create_jira_tasks_via_mcp.py

The "MCP way" sibling to create_jira_tasks_from_analysis.py. Instead of a
separate Groq call to draft tickets plus raw REST calls to Jira, this uses
the Claude API's MCP connector: Claude reasons about each gap record,
searches Jira for duplicates, and creates the ticket - all as tool calls
inside one Messages API request per gap, via Atlassian's remote MCP server.

This is the reproducible/scriptable counterpart to mcp_live_triage_demo.md
(same MCP server, but scripted end-to-end instead of a guided chat).

Environment variables:
  ANTHROPIC_API_KEY   - your Anthropic API key
  JIRA_MCP_TOKEN       - bearer token for Atlassian's MCP server. Try your
                          existing Jira API token first - Atlassian's docs
                          say the server accepts OAuth 2.1 *or* API tokens.
                          If auth fails, you'll need an OAuth access token
                          instead (the kind Claude Code obtained via `/mcp`).
  JIRA_PROJECT_KEY    - e.g. "KAN"

Cost: at ~5 gap records and Sonnet-tier pricing, this runs a few cents total.
See MODEL below to swap between Opus 5 (default, most capable) and Sonnet 5
(cheaper, plenty capable for this task).
"""

import os
import json
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

MCP_SERVER_URL = "https://mcp.atlassian.com/v1/mcp/authv2"
MCP_SERVER_NAME = "atlassian"
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]
JIRA_MCP_TOKEN = os.environ["JIRA_MCP_TOKEN"]

# claude-opus-5 (default) is the most capable; swap to claude-sonnet-5 for a
# cheaper run - both are more than enough for this task.
MODEL = "claude-opus-5"


def process_gap(gap: dict) -> str:
    """Ask Claude to triage one gap record end-to-end via Jira's MCP tools."""
    review_ids = gap.get("evidence", {}).get("review_ids", [])
    if not review_ids:
        return f"{gap.get('gap_id', '?')}: skipped - no evidence (no gap without evidence)"

    prompt = f"""
You are triaging a review-analysis gap record for the Jira project "{JIRA_PROJECT_KEY}".

Gap record:
{json.dumps(gap, indent=2)}

Steps:
1. Search Jira for existing issues that might already cover this need, using
   a few keywords from the "need" field.
2. If a close match exists, report it and STOP - do not create a duplicate.
3. If no close match exists, draft a ticket:
   - summary: short title phrased as the user's need
   - description with labeled sections: Need, Confidence (score + rationale
     verbatim from the input), Evidence (review_count + a few review_ids),
     Verdict
   - priority: floor is High for IGNORED/MISUNDERSTOOD, Medium for
     UNDER-PRIORITIZED; raise above the floor only if confidence >= 0.85
   - labels: the verdict (lowercase-hyphenated) plus "user-feedback"
4. Create the ticket in the "{JIRA_PROJECT_KEY}" project using the Jira MCP
   tools.
5. Report back the created issue key and URL, or the duplicate you found -
   one or two sentences, no extra commentary.
"""

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4096,
        betas=["mcp-client-2025-11-20"],
        mcp_servers=[
            {
                "type": "url",
                "url": MCP_SERVER_URL,
                "name": MCP_SERVER_NAME,
                "authorization_token": JIRA_MCP_TOKEN,
            }
        ],
        tools=[{"type": "mcp_toolset", "mcp_server_name": MCP_SERVER_NAME}],
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    return f"{gap.get('gap_id', '?')}: {text}"


def process_analysis_json(json_path: str) -> list:
    with open(json_path, encoding="utf-8") as f:
        gaps = json.load(f)
    results = []
    for gap in gaps:
        result = process_gap(gap)
        print(result)
        print("---")
        results.append(result)
    return results


if __name__ == "__main__":
    process_analysis_json("analysis_results.json")
