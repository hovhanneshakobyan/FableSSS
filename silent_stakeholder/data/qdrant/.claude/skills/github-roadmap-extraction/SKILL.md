---
name: github-roadmap-extraction
description: Read-only extraction of a public repository's roadmap (Issues, Milestones, Labels, PRs) via the GitHub REST API into a normalized, evidence-citable record format. Use when pulling "what the team is building" for a product from its GitHub repo — as the backlog/roadmap side of a gap analysis, not for managing your own backlog.
---

# GitHub Roadmap Extraction

Adapted from the read-side of
[gringolito/github-backlog-management-skill](https://github.com/gringolito/github-backlog-management-skill).
That project manages *your own* backlog with write access (`gh`, Projects v2,
INVEST gates). This skill only *reads* someone else's public repo to
reconstruct their roadmap — no auth, no writes, no assumption you control the
target repository.

## Quick start

1. Resolve `owner/repo` for the target product (check the product's website
   footer, Play Store/App Store dev links, or search GitHub directly).
   **Confirm the current canonical slug, not just a historically-known one**:
   repos get renamed/transferred (e.g. K-9 Mail's repo is now
   `thunderbird/thunderbird-android`, not the historical `k9mail/k-9`).
   GitHub's REST endpoints (`/repos/...`, `/issues`, `/milestones`) redirect
   transparently from an old slug to the new one, but **the Search API does
   not** — `repo:<old-slug>` in a search query returns a 422 error. Always
   resolve and use the current slug, especially for any Search API call.
2. Pull **issues** (open + closed — closed issues show what was already
   prioritized and shipped, which matters for "already addressed" checks),
   **milestones**, and **labels**.
3. Filter out pull requests (the `/issues` endpoint returns both; a PR has a
   `pull_request` key in the response — drop those).
4. Normalize into the schema below. Every record's `id` becomes the citation
   key any downstream gap analysis must reference.
5. Note repo-level context once: stars, last-commit recency, whether Issues
   are even actively triaged (a repo with 90% unlabeled issues and no
   milestones is a different kind of "roadmap" than a well-groomed one —
   record this, it affects confidence later).

## Fetching (no `gh` CLI dependency — plain REST)

Unauthenticated requests are capped at 60/hr per IP; set `GITHUB_TOKEN` (a
plain read-only PAT, `public_repo` scope is enough) to raise this to 5000/hr.
Always paginate via the `Link` response header, don't assume one page is
everything.

```python
import os
import requests

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}
if token := os.environ.get("GITHUB_TOKEN"):
    HEADERS["Authorization"] = f"Bearer {token}"


def paginated_get(url: str, params: dict | None = None) -> list[dict]:
    results: list[dict] = []
    while url:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        results.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None  # params are baked into the `next` URL already
    return results


def fetch_roadmap(owner: str, repo: str) -> dict:
    issues = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        params={"state": "all", "per_page": 100},
    )
    issues = [i for i in issues if "pull_request" not in i]
    milestones = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/milestones",
        params={"state": "all", "per_page": 100},
    )
    labels = paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/labels")
    return {"issues": issues, "milestones": milestones, "labels": labels}
```

## Normalized record schema

Every roadmap item becomes one record, keyed by a stable, citable `id`:

```json
{
  "id": "owner/repo#1234",
  "title": "Add offline mode",
  "state": "open",
  "labels": ["type:feature", "priority:P2"],
  "milestone": "v4.2.0",
  "milestone_due_on": "2026-09-01",
  "created_at": "2025-11-02T10:00:00Z",
  "updated_at": "2026-06-10T08:00:00Z",
  "closed_at": null,
  "comments": 14,
  "reactions": 32,
  "body_excerpt": "first ~500 chars of the issue body",
  "url": "https://github.com/owner/repo/issues/1234"
}
```

`id` is what every gap's evidence trace cites — never paraphrase an issue
without recording its `id`.

## Signals worth extracting beyond "does an issue exist"

Raw existence isn't enough to judge IGNORED vs. UNDER-PRIORITIZED vs.
MISUNDERSTOOD — pull these too:

- **Staleness**: `updated_at` far in the past relative to `created_at` and to
  now → candidate for UNDER-PRIORITIZED even if an issue nominally exists.
- **No milestone / unlabeled priority**: an open issue with no `priority:*`
  label and no milestone is functionally not on the roadmap, even though it
  technically exists — don't count it as "addressed."
- **Engagement without action**: high `comments`/`reactions` on an old, open,
  unmilestoned issue is a strong signal the team knows about demand but
  hasn't acted — this is the clearest form of UNDER-PRIORITIZED.
- **Closed-as-not-planned**: check `state_reason` (`"not_planned"` vs
  `"completed"`) on closed issues — a need explicitly rejected is different
  from one that was actually shipped.
- **Scope mismatch**: an issue that exists but whose title/body addresses a
  narrower or different problem than what users are actually describing is
  the MISUNDERSTOOD case — this requires reading the issue body against the
  user-signal cluster, not just keyword-matching titles.

## Label naming gotcha

Don't assume label names follow a particular convention without checking —
e.g. K-9 Mail/Thunderbird for Android uses `"type: bug"` (colon **and a
space**), not `"type:bug"`. An exact-match filter built on the wrong
assumption will silently match zero labels instead of erroring. Always fetch
`/repos/{owner}/{repo}/labels` and match against the real strings returned.

## What NOT to do

- Don't treat "an issue with a similar-sounding title exists" as proof the
  need is covered — read the body; titles lie or oversimplify constantly.
- Don't ignore closed issues — closing without shipping (`not_planned`) is
  evidence too.
- Don't fabricate an issue number or quote issue text you didn't actually
  fetch. If you can't access the repo (private, rate-limited, no Issues
  enabled), say so explicitly rather than guessing at roadmap contents.
