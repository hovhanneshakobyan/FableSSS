"""
create_jira_tasks_from_analysis.py

Pipeline:
  1. Read silent_stakeholder's gap-analysis output (silent_stakeholder/data/gaps.json
     - a JSON object with a top-level "gaps" list, see the schema below).
  2. Enforce the "no evidence, no gap" rule: any record with an empty
     evidence.reviews list is skipped and logged, never ticketed.
  3. Ask an LLM to phrase a short ticket summary from the need - it does NOT
     draft the numbers. Confidence, verdict, review citations, and related
     backlog issues are taken verbatim from the gap record and formatted in
     code, so nothing in the ticket body can drift from what the pipeline
     actually computed.
  4. Search Jira for existing similar tickets (dedup check).
  5. If no close match exists, create the ticket via Jira's REST API.

Actual input schema - silent_stakeholder/data/gaps.json, "gaps": [...] with
records like:
{
  "id": "battery",
  "need": "Battery usage could be improved though.",
  "quote": "...",                       # the single sourced quote
  "quote_cite": "rev:80b2d9ba",
  "quote_star": 4,
  "symptom_terms": [...], "mechanism_terms": [...],
  "confidence": 46,                     # int 0-100, NOT a 0-1 float
  "score": {"raw": ..., "E": {...}, "L": {...}, "penalties": [...], "formula": "..."},
  "verdict": "UNDER-PRIORITIZED",       # IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD
  "why": "...", "reason": "...",
  "metrics": {
    "n_reviews": 53, "n_issues": 37, "prevalence": ..., "mean_star": ...,
    "star_deficit": ..., "months_hit": ..., "epics": [...],
    "bridge": [{"cite": "k9#1066", "corpus": "k9_issues",
                "symptom": "...", "mechanism": "..."}, ...]
  },
  "evidence": {
    "reviews": [{"cite": "rev:...", "star": 4, "date": "2016-...",
                 "families": [...], "lam": ..., "text": "..."}, ...]
    # this is a CITED SAMPLE, not the full set - metrics.n_reviews is the
    # true count (metrics.n_issues is the backlog side, not review count)
  }
}

Requirements:
  pip install openai anthropic requests --break-system-packages

Environment variables you need to set (see .env):
  LLM_PROVIDER        - "groq" (default here) or "anthropic"
  GROQ_API_KEY         - required if LLM_PROVIDER=groq
  ANTHROPIC_API_KEY    - required if LLM_PROVIDER=anthropic
  JIRA_BASE_URL        - e.g. "https://unicornidea.atlassian.net"
  JIRA_EMAIL           - the Atlassian account email
  JIRA_API_TOKEN       - create one at https://id.atlassian.com/manage-profile/security/api-tokens
  JIRA_PROJECT_KEY     - e.g. "KAN"
  JIRA_ISSUE_TYPE      - must match a real issue type name on the project,
                         e.g. "Задание"

Usage:
  python3 create_jira_tasks_from_analysis.py <path-to-gaps.json>
"""

import os
import sys
import json
import requests

# ---------- LLM provider selection (summary phrasing only) ----------
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

if LLM_PROVIDER == "groq":
    from openai import OpenAI  # pip install openai --break-system-packages

    llm_client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )
    DRAFT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
else:
    from anthropic import Anthropic  # pip install anthropic --break-system-packages

    llm_client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    DRAFT_MODEL = "claude-sonnet-5"


def call_llm(prompt: str, max_tokens: int = 60) -> str:
    if LLM_PROVIDER == "groq":
        resp = llm_client.chat.completions.create(
            model=DRAFT_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    else:
        resp = llm_client.messages.create(
            model=DRAFT_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


# ---------- Jira config ----------
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]
JIRA_ISSUE_TYPE = os.environ.get("JIRA_ISSUE_TYPE", "Task")

AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json"}

# Verdict -> baseline priority floor. IGNORED and MISUNDERSTOOD are worse
# roadmap failures than UNDER-PRIORITIZED (something is at least in motion),
# so they get a higher floor before confidence is factored in.
VERDICT_PRIORITY_FLOOR = {
    "IGNORED": "High",
    "MISUNDERSTOOD": "High",
    "UNDER-PRIORITIZED": "Medium",
}
PRIORITY_RAISE = {"High": "Highest", "Medium": "High"}
CONFIDENCE_RAISE_BAR = 85  # gap["confidence"] is 0-100, not 0-1


def enforce_evidence_gate(gap: dict) -> bool:
    """No evidence, no gap. Returns False if this record must be skipped."""
    return len(gap.get("evidence", {}).get("reviews", [])) > 0


def draft_summary(gap: dict) -> str:
    """LLM phrases the title only - every fact in the ticket body is built
    deterministically in build_description/build_priority, never drafted."""
    prompt = (
        "Rephrase this app-review need as a short Jira ticket summary "
        "(under 12 words), phrased as the user's need. Reply with ONLY "
        "the summary text - no quotes, no trailing punctuation, no preamble.\n\n"
        f"{gap['need']}"
    )
    return call_llm(prompt, max_tokens=40).strip().strip('"')


def build_priority(gap: dict) -> str:
    floor = VERDICT_PRIORITY_FLOOR[gap["verdict"]]
    if gap["confidence"] >= CONFIDENCE_RAISE_BAR:
        return PRIORITY_RAISE.get(floor, floor)
    return floor


def build_description(gap: dict) -> str:
    """Every number here comes straight from the gap record - the LLM never
    touches this text, so it can't drift from what the pipeline computed."""
    metrics = gap["metrics"]
    reviews = gap["evidence"]["reviews"]

    lines = [
        "Need:",
        gap["need"],
        f'Source quote ({gap["quote_cite"]}, {gap["quote_star"]}★): "{gap["quote"]}"',
        "",
        "Confidence:",
        f'Score: {gap["confidence"]} (raw {gap["score"]["raw"]})',
        f'Rationale: "{gap["reason"]}"',
        f'Why: "{gap["why"]}"',
        "",
        "Evidence:",
        f'review_count: {metrics["n_reviews"]} ({len(reviews)} cited; '
        f'prevalence {metrics["prevalence"]}%, mean star {metrics["mean_star"]}, '
        f'star deficit {metrics["star_deficit"]}, {metrics["months_hit"]} months hit)',
    ]
    for r in reviews:
        snippet = r["text"][:140].rstrip()
        lines.append(f'- {r["cite"]} ({r["star"]}★, {r["date"]}) - "{snippet}..."')
    if metrics.get("bridge"):
        bridge_cites = sorted({b["cite"] for b in metrics["bridge"]})
        lines.append(f'Related backlog (different vocabulary): {", ".join(bridge_cites)}')
    if metrics.get("epics"):
        lines.append(f'Epics touched: {", ".join(metrics["epics"])}')
    lines += ["", "Verdict:", f'{gap["verdict"]} - {gap["why"]}']

    return "\n".join(lines)


def draft_ticket(gap: dict) -> dict:
    return {
        "summary": draft_summary(gap),
        "description": build_description(gap),
        "priority": build_priority(gap),
        "labels": [gap["verdict"].lower(), "user-feedback"],
        # symptom_terms only, not mechanism_terms: mechanism_terms exist to
        # bridge review vocabulary to backlog engineering-speak (e.g.
        # security -> ["keys", "green", "signing"]) and are too generic for
        # duplicate search - "left", "mailing", "high", "green" false-matched
        # unrelated tickets via their pasted review-text descriptions.
        "search_keywords": gap["symptom_terms"][:5],
    }


# ---------- Step 2: dedup check against existing Jira issues ----------
def find_similar_issues(keywords: list, limit: int = 5) -> list:
    """JQL search using the gap's own symptom_terms - these are what the
    pipeline already extracted as the topical (not bridging) vocabulary.

    Two fixes over a naive text ~ "word1 word2" search:
    - OR each keyword individually: text ~ "w1 w2" is a phrase-ish match in
      JQL, not an OR across terms, so joining with spaces silently missed
      real duplicates (e.g. "hotmail microsoft" matched nothing, "hotmail"
      alone found KAN-7).
    - Search summary only, not text (summary+description+comments): these
      tickets have full pasted review bodies as descriptions, so a
      full-text OR let single generic words match unrelated tickets."""
    or_clause = " OR ".join(f'summary ~ "{kw}"' for kw in keywords)
    jql = f'project = {JIRA_PROJECT_KEY} AND ({or_clause}) ORDER BY created DESC'
    resp = requests.get(
        f"{JIRA_BASE_URL}/rest/api/3/search/jql",
        auth=AUTH,
        headers=HEADERS,
        params={"jql": jql, "maxResults": limit, "fields": "summary,status"},
    )
    resp.raise_for_status()
    return resp.json().get("issues", [])


def _text_to_adf(text: str) -> dict:
    """ADF text nodes can't contain literal newlines - each line becomes its own paragraph."""
    lines = text.split("\n")
    content = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        if line.strip()
        else {"type": "paragraph", "content": []}
        for line in lines
    ]
    return {"type": "doc", "version": 1, "content": content}


# ---------- Step 3: create the Jira issue ----------
def create_jira_task(ticket: dict) -> dict:
    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": ticket["summary"],
            "description": _text_to_adf(ticket["description"]),
            "issuetype": {"name": JIRA_ISSUE_TYPE},
            "priority": {"name": ticket["priority"]},
            "labels": ticket["labels"],
        }
    }
    resp = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue",
        auth=AUTH,
        headers=HEADERS,
        json=payload,
    )
    if not resp.ok:
        print(f"    Jira error {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()


# ---------- Main pipeline ----------
def process_gaps(gaps: list, dry_run: bool = False) -> list:
    results = []

    for gap in gaps:
        if not enforce_evidence_gate(gap):
            print(f"Skipping {gap.get('id', '?')} - no evidence (no gap without evidence)")
            results.append({"id": gap.get("id"), "status": "skipped_no_evidence"})
            continue

        ticket = draft_ticket(gap)
        print(
            f"--- {gap['id']} | {gap['verdict']} | confidence {gap['confidence']} "
            f"| evidence: {gap['metrics']['n_reviews']} reviews ---"
        )
        print(f"    Draft summary: {ticket['summary']} (priority: {ticket['priority']})")

        similar = find_similar_issues(ticket["search_keywords"])
        if similar:
            print(f"    Skipped - {len(similar)} similar issue(s) already exist:")
            for issue in similar:
                print(f"      {issue['key']}: {issue['fields']['summary']}")
            results.append({
                "id": gap.get("id"),
                "status": "skipped_duplicate",
                "similar_issues": [i["key"] for i in similar],
            })
            continue

        if dry_run:
            print(f"    [dry-run] Would create - labels: {ticket['labels']}")
            results.append({
                "id": gap.get("id"),
                "status": "dry_run_would_create",
                "ticket": ticket,
            })
            continue

        created = create_jira_task(ticket)
        issue_url = f"{JIRA_BASE_URL}/browse/{created['key']}"
        print(f"    Created: {created['key']} -> {issue_url}")
        results.append({
            "id": gap.get("id"),
            "status": "created",
            "issue_key": created["key"],
            "issue_url": issue_url,
        })

    return results


def process_analysis_json(json_path: str, dry_run: bool = False) -> list:
    with open(json_path, encoding="utf-8") as f:
        gaps = json.load(f)["gaps"]
    return process_gaps(gaps, dry_run=dry_run)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    if len(args) != 1:
        print("Usage: python3 create_jira_tasks_from_analysis.py <path-to-gaps.json> [--dry-run]")
        sys.exit(1)
    process_analysis_json(args[0], dry_run=dry_run)
