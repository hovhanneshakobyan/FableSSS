"""
watch_new_issues.py

Polls a GitHub repo's Issues API and posts a Slack notification for every
issue created since the last check. State (the highest issue id/number seen
so far) is kept in state.json next to this script, so re-running - or
restarting after a crash - never re-notifies for the same issue twice.

On first run (no state.json yet), it records the current newest issue as the
baseline WITHOUT notifying - otherwise every historical issue in the repo
would fire a Slack message.

Environment variables:
  GITHUB_REPO         - "owner/repo", defaults to "thunderbird/thunderbird-android"
                         (the repo the review-gap analysis in this project tracks)
  GITHUB_TOKEN         - optional; raises the GitHub API rate limit from 60/hr
                          to 5000/hr. Needs no scopes for public repos.
  SLACK_WEBHOOK_URL    - required; an incoming webhook URL from a Slack app
  POLL_INTERVAL_SECONDS - how often to check, default 60

Usage:
  python3 watch_new_issues.py            # poll forever until Ctrl+C
  python3 watch_new_issues.py --once     # check once and exit (e.g. for cron)

Requirements:
  pip install requests python-dotenv

Config file:
  A .env file next to this script (gitignored) is loaded automatically if
  present. Example:
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    GITHUB_REPO=owner/repo
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

GITHUB_REPO = os.environ.get("GITHUB_REPO", "thunderbird/thunderbird-android")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))

STATE_FILE = Path(__file__).parent / "state.json"

GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def load_last_seen_id() -> Optional[int]:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text()).get("last_seen_id")


def save_last_seen_id(issue_id: int) -> None:
    STATE_FILE.write_text(json.dumps({"last_seen_id": issue_id}))


def fetch_recent_issues() -> list:
    """Newest first. GitHub's issues endpoint also returns pull requests -
    those are filtered out since they carry a "pull_request" key."""
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers=GITHUB_HEADERS,
        params={"state": "all", "sort": "created", "direction": "desc", "per_page": 30},
    )
    resp.raise_for_status()
    return [issue for issue in resp.json() if "pull_request" not in issue]


def notify_slack(issue: dict) -> None:
    text = f"New issue in {GITHUB_REPO}: <{issue['html_url']}|#{issue['number']} {issue['title']}> (by {issue['user']['login']})"
    resp = requests.post(SLACK_WEBHOOK_URL, json={"text": text})
    resp.raise_for_status()


def check_once() -> None:
    issues = fetch_recent_issues()
    if not issues:
        return

    last_seen_id = load_last_seen_id()

    if last_seen_id is None:
        save_last_seen_id(issues[0]["id"])
        print(f"Baseline set: newest issue is #{issues[0]['number']} - future runs will notify from here")
        return

    new_issues = [issue for issue in issues if issue["id"] > last_seen_id]
    for issue in reversed(new_issues):  # oldest-first, so Slack messages land in chronological order
        notify_slack(issue)
        print(f"Notified: #{issue['number']} {issue['title']}")

    if new_issues:
        save_last_seen_id(issues[0]["id"])


def main() -> None:
    if "--once" in sys.argv:
        check_once()
        return

    print(f"Watching {GITHUB_REPO} for new issues every {POLL_INTERVAL_SECONDS}s (Ctrl+C to stop)")
    while True:
        check_once()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
