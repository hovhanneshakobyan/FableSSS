"""Data-access layer for The Silent Stakeholder.

One implementation, three consumers:
  1. the deterministic pipeline
  2. Claude Agent SDK tool definitions (live defense)
  3. an optional MCP server (mcp_server.py wraps these verbatim)

Every function is pure, offline, and sub-100ms. No network. No LLM.
"""
from __future__ import annotations
import json, re, os, statistics
from functools import lru_cache

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")


@lru_cache(maxsize=1)
def _reviews() -> list[dict]:
    rows = json.load(open(os.path.join(ROOT, "k9_reviews.json")))
    for r in rows:
        r["_lc"] = (r.get("text") or "").lower()
    return rows


@lru_cache(maxsize=1)
def _issues() -> list[dict]:
    rows = json.load(open(os.path.join(ROOT, "k9_issues_all.json")))
    out = []
    for i in rows:
        body = i.get("body") or ""
        labels = [l["name"] for l in i.get("labels", [])]
        out.append({
            "number": i["number"], "title": i.get("title") or "", "body": body,
            "state": i["state"], "created_at": i["created_at"][:10],
            "closed_at": (i.get("closed_at") or "")[:10] or None,
            "html_url": i.get("html_url", ""), "comments": i.get("comments", 0),
            "labels": labels,
            "type_label": next((l.split(": ", 1)[1] for l in labels
                                if l.startswith("type: ")), None),
            "milestone": (i.get("milestone") or {}).get("title"),
            "_lc": ((i.get("title") or "") + " " + body).lower(),
        })
    return out


@lru_cache(maxsize=1)
def _sentences() -> list[dict]:
    return json.load(open(os.path.join(ROOT, "k9_sentences.json")))


def _rx(terms: str | list[str]) -> re.Pattern:
    if isinstance(terms, str):
        terms = [terms]
    return re.compile("|".join(rf"\b{re.escape(t.lower())}\b" if " " not in t
                               else re.escape(t.lower()) for t in terms))


# ---------------------------------------------------------------- search
def search_reviews(query: str, star_min: int = 1, star_max: int = 5,
                   min_chars: int = 0, limit: int = 20) -> dict:
    """Substring/keyword search over the 1,560 reviews. Returns matches + stats."""
    rx = _rx(query)
    hits = [r for r in _reviews()
            if rx.search(r["_lc"]) and star_min <= r["star"] <= star_max
            and r["chars"] >= min_chars]
    stars = [h["star"] for h in hits]
    return {
        "query": query, "n": len(hits), "corpus_n": len(_reviews()),
        "pct": round(100 * len(hits) / len(_reviews()), 2),
        "mean_star": round(statistics.mean(stars), 2) if stars else None,
        "corpus_mean_star": 3.43,
        "star_hist": {s: stars.count(s) for s in range(1, 6)},
        "results": [{"id": h["id"], "star": h["star"], "date": h["date"],
                     "text": h["text"][:400]} for h in hits[:limit]],
    }


def search_issues(query: str, state: str | None = None,
                  type_label: str | None = None, limit: int = 20) -> dict:
    """Search the 1,718 in-window GitHub issues."""
    rx = _rx(query)
    hits = [i for i in _issues() if rx.search(i["_lc"])
            and (state is None or i["state"] == state)
            and (type_label is None or i["type_label"] == type_label)]
    return {
        "query": query, "n": len(hits), "corpus_n": len(_issues()),
        "pct": round(100 * len(hits) / len(_issues()), 2),
        "open_n": sum(1 for h in hits if h["state"] == "open"),
        "results": [{"number": h["number"], "title": h["title"], "state": h["state"],
                     "created_at": h["created_at"], "closed_at": h["closed_at"],
                     "type_label": h["type_label"], "milestone": h["milestone"],
                     "comments": h["comments"], "url": h["html_url"]} for h in hits[:limit]],
    }


# ---------------------------------------------------------------- the core metric
def polarity(symptom_terms: list[str], mechanism_terms: list[str]) -> dict:
    """Polarity Inversion Index — the framing-mismatch detector.

    pol(T) = share of reviews matching T / share of issues matching T
    PII    = log2(pol(symptom) / pol(mechanism))
    PII > 0 means users lead on symptom AND devs lead on mechanism.
    """
    import math
    R, I = _reviews(), _issues()

    def pol(terms):
        rx = _rx(terms)
        a = sum(1 for r in R if rx.search(r["_lc"]))
        b = sum(1 for i in I if rx.search(i["_lc"]))
        pr, pi = a / len(R), max(b / len(I), 1 / len(I))
        return a, b, pr / pi

    sa, sb, sp = pol(symptom_terms)
    ma, mb, mp = pol(mechanism_terms)
    pii = math.log2(sp / mp) if mp > 0 else float("inf")
    return {
        "symptom": {"terms": symptom_terms, "reviews": sa, "issues": sb,
                    "polarity": round(sp, 2)},
        "mechanism": {"terms": mechanism_terms, "reviews": ma, "issues": mb,
                      "polarity": round(mp, 2)},
        "pii": round(pii, 2), "pii_norm": round(min(max(pii / 4, 0), 1), 2),
        "passes_gate": pii >= 1.0,
    }


def bridge(symptom_terms: list[str], mechanism_terms: list[str],
           limit: int = 10) -> dict:
    """Documents where BOTH vocabularies co-occur — proves the causal link is
    witnessed in the corpus rather than asserted. Gate requires >= 3."""
    S, M = _rx(symptom_terms), _rx(mechanism_terms)
    ri = [i for i in _issues() if S.search(i["_lc"]) and M.search(i["_lc"])]
    rr = [r for r in _reviews() if S.search(r["_lc"]) and M.search(r["_lc"])]
    return {
        "bridge_count": len(ri) + len(rr), "passes_gate": len(ri) + len(rr) >= 3,
        "issues": [{"number": i["number"], "title": i["title"], "state": i["state"],
                    "url": i["html_url"]} for i in ri[:limit]],
        "reviews": [{"id": r["id"], "star": r["star"], "date": r["date"],
                     "text": r["text"][:200]} for r in rr[:limit]],
    }


# ---------------------------------------------------------------- lookup
def get_review(review_id: str) -> dict | None:
    """Full record by UUID (prefix match allowed) + its labeled sentences."""
    r = next((x for x in _reviews() if x["id"].startswith(review_id)), None)
    if not r:
        return None
    return {k: v for k, v in r.items() if k != "_lc"} | {
        "sentences": [{"text": s["text"], "intention": s["intention"],
                       "topic": s["topic"]}
                      for s in _sentences() if s["review_id"] == r["id"]]}


def get_issue(number: int) -> dict | None:
    i = next((x for x in _issues() if x["number"] == int(number)), None)
    return {k: v for k, v in i.items() if k != "_lc"} if i else None


def resolution_lag(number: int) -> dict:
    """BACKTEST ONLY — never feed into scoring. Leaks the future."""
    import datetime
    i = get_issue(number)
    if not i:
        return {"error": "not found"}
    if not i["closed_at"]:
        return {"number": number, "state": "open", "days": None,
                "verdict": "STILL OPEN in 2026"}
    d = (datetime.date.fromisoformat(i["closed_at"])
         - datetime.date.fromisoformat(i["created_at"])).days
    return {"number": number, "days": d, "years": round(d / 365.25, 1),
            "closed_at": i["closed_at"], "type_label": i["type_label"]}


TOOLS = [search_reviews, search_issues, polarity, bridge,
         get_review, get_issue, resolution_lag]
