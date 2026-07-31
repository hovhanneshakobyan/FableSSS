"""KB layer 1 — data/raw/*.json -> normalized documents. No SQLite, no network.

Every document is {"id", "text", "payload"}:
  id       point id in Qdrant (uuid for reviews, issue number, row index)
  text     the string that gets embedded — short, dense, no boilerplate
  payload  everything a filter or a citation could ever need

Derived fields (ym, star_band, days_open, type_label) are computed here and
nowhere else, so the vector payload and the keyword count can never disagree.
AS_OF is frozen: staleness must not drift between two runs.
"""
from __future__ import annotations
import datetime, json, os
from functools import lru_cache

AS_OF = "2026-07-31"                 # FROZEN. Never datetime.now().
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")

# Issue bodies run to thousands of chars; bge truncates at 512 tokens anyway.
# The full body still lands in the payload — only the embedded string is cut.
BODY_CHARS = 600

# Truncating at BODY_CHARS drops 56% of all body text, and a phrase past the cut
# is near-unfindable (measured recall@10 36% vs 88% for text inside the window).
# So issues are indexed as overlapping chunks instead. ~900 chars sits under
# bge's 512-token limit; the cap keeps one 100k-char log dump from becoming 227
# points. Chunk ids are number*100+ix, so a point id still names its issue.
CHUNK, OVERLAP, MAX_CHUNKS = 900, 150, 24


@lru_cache(maxsize=8)
def raw(name: str) -> list[dict]:
    with open(os.path.join(RAW, name), encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def review_window() -> tuple[str, str]:
    """The dates reviews actually cover: 2015-11-29 -> 2017-05-02.

    Issues run 2015-03-15 -> 2017-12-31, so 37% of the backlog sits outside
    the period users were talking. Comparing rates across the two full corpora
    silently compares different windows — see KB.polarity(aligned=True).
    """
    dates = [r["date"] for r in raw("k9_reviews.json")]
    return min(dates), max(dates)


def _days(start: str, end: str) -> int:
    return (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days


# ------------------------------------------------------------------ loaders
def reviews() -> list[dict]:
    """k9_reviews.json — 1,560 Play Store reviews, 2015-11-29 -> 2017-05-02."""
    out = []
    for r in raw("k9_reviews.json"):
        star = int(r["star"])
        out.append({"id": r["id"], "text": r["text"], "payload": {
            "source": "k9_reviews", "app": "k9",
            "review_id": r["id"], "text": r["text"], "star": star,
            "date": r["date"], "ym": r["date"][:7],
            "star_band": "low" if star <= 2 else "mid" if star == 3 else "high",
            "chars": int(r["chars"]), "version_id": int(r["version_id"])}})
    return out


def sentences() -> list[dict]:
    """k9_sentences.json — 4,224 third-party labelled sentences.

    Labels are noisy: corroboration, never gospel. star/date are joined back
    from the parent review so a sentence can be filtered on its own.
    """
    parent = {r["id"]: r for r in raw("k9_reviews.json")}
    out = []
    for i, s in enumerate(raw("k9_sentences.json"), start=1):
        p = parent.get(s["review_id"], {})
        out.append({"id": i, "text": s["text"], "payload": {
            "source": "k9_sentences", "app": "k9",
            "sentence_id": i, "review_id": s["review_id"], "text": s["text"],
            "intention": s["intention"], "topic": s["topic"],
            "star": int(s.get("star", p.get("star", 0)) or 0),
            "date": p.get("date")}})
    return out


def _issues(filename: str, app: str) -> list[dict]:
    """Raw GitHub JSON -> issue documents. days_open measured against AS_OF."""
    out = []
    for i in raw(filename):
        title, body = i.get("title") or "", i.get("body") or ""
        labels = [l["name"] for l in i.get("labels") or []]
        created = i["created_at"][:10]
        closed = (i.get("closed_at") or "")[:10] or None
        reason = i.get("state_reason")
        out.append({
            "id": i["number"],
            "text": f"{title} {body[:BODY_CHARS]}".strip(),
            "payload": {
                "source": f"{app}_issues", "app": app,
                "number": i["number"], "title": title,
                "text": f"{title} {body[:BODY_CHARS]}".strip(), "body": body,
                "state": i["state"], "created_at": created, "closed_at": closed,
                "ym": created[:7], "days_open": _days(created, closed or AS_OF),
                "type_label": next((l.split(": ", 1)[1] for l in labels
                                    if l.startswith("type: ")), None),
                "labels": labels,
                "milestone": (i.get("milestone") or {}).get("title"),
                "comments": i.get("comments", 0), "url": i.get("html_url", ""),
                "state_reason": reason,
                "is_stale_open": i["state"] == "open",
                "is_needs_info": "status: needs information" in labels,
                "is_not_planned": reason == "not_planned"}})
    return out


def k9_issues() -> list[dict]:
    """k9_issues_all.json — 1,718 thunderbird/thunderbird-android issues."""
    return _issues("k9_issues_all.json", "k9")


def split(text: str, size: int = CHUNK, overlap: int = OVERLAP,
          cap: int = MAX_CHUNKS) -> list[str]:
    """Overlapping windows, cut on whitespace so no chunk starts mid-word."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out, start, step = [], 0, size - overlap
    while start < len(text) and len(out) < cap:
        end = start + size
        if end < len(text):                       # snap back to a word boundary
            cut = text.rfind("\n", start + step, end)
            if cut == -1:
                cut = text.rfind(" ", start + step, end)
            end = cut if cut != -1 else end
        chunk = text[start:end].strip()
        if chunk:
            out.append(chunk)
        start = max(end - overlap, start + step)
    return out


def issue_chunks() -> list[dict]:
    """k9_issues as retrievable chunks — what actually goes into Qdrant.

    The full body is NOT copied onto every chunk: 24 copies of a 100k-char
    dump is 2.4MB of payload for nothing. The raw layer already has bodies,
    and `KB.get` reads them from there.
    """
    out = []
    for d in k9_issues():
        p = d["payload"]
        meta = {k: v for k, v in p.items() if k not in ("body", "text")}
        parts = split(f"{p['title']}\n{p['body']}".strip())
        for ix, part in enumerate(parts):
            out.append({"id": p["number"] * 100 + ix, "text": part,
                        "payload": {**meta, "text": part,
                                    "chunk": ix, "n_chunks": len(parts)}})
    return out


def ap_issues() -> list[dict]:
    """ap_issues.json — 1,000 AntennaPod issues. Negative control only."""
    return _issues("ap_issues.json", "antennapod")


# Name -> (loader, expected row count). Counts are asserted at load time:
# a silent truncation of a raw file must fail loudly, not ship a smaller index.
SOURCES = {
    "k9_reviews":   (reviews,   1560),
    "k9_issues":    (k9_issues, 1718),
    "k9_sentences": (sentences, 4224),
    "ap_issues":    (ap_issues, 1000),
}

# Embedded into Qdrant. ap_issues is deliberately NOT here: the control is used
# by comparing term rates against K-9, and a rate comes from keyword counting.
# Nothing asks a control corpus for its nearest neighbours, so nothing embeds it.
COLLECTIONS = ("k9_reviews", "k9_issues", "k9_sentences")

# Collections whose points are chunks, not documents -> {collection: group key}.
# Retrieval happens at chunk level; results are collapsed back to documents, so
# one long issue matching in four places is still one hit.
CHUNKED = {"k9_issues": "number"}

# What gets embedded, when that differs from the raw document.
INDEXED_AS = {"k9_issues": issue_chunks}


def load(name: str) -> list[dict]:
    """Raw documents for one corpus, with its row-count assertion applied.

    One row in, one document out — this is the counting layer. Chunking lives
    in `index_docs`, so a rate per 1,000 documents never becomes a rate per
    1,000 chunks.
    """
    loader, want = SOURCES[name]
    docs = loader()
    if len(docs) != want:
        raise SystemExit(f"{name}: got {len(docs)} documents, expected {want}")
    return docs


def index_docs(name: str) -> list[dict]:
    """The points that belong in Qdrant for one collection."""
    load(name)                               # keep the row-count assertion
    return INDEXED_AS[name]() if name in INDEXED_AS else load(name)
