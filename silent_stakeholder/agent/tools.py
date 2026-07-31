"""The agent's tool belt — a thin, flat wrapper over `kb`.

Design rules, all of them driven by weak free-tier models:

  * Flat scalar arguments only. No nested dicts, no `where` grammar — a 7B model
    will produce malformed JSON for anything shaped. Filters are separate ints.
  * Terms arrive as one comma-separated string; `kb` already splits on commas.
  * Every result is JSON with its denominator attached (`n_matched/n_scanned`),
    so a count can never be quoted without the corpus it came from.
  * Returns are truncated hard. A 100k-char issue body would eat the context
    window and teach the model nothing.

One KB per process, and one call at a time — see `_LOCK` below. `KB.qc` stays
lazy, so the lexical tools (count_terms/polarity/control — raw JSON scans) keep
working even while a `kb build` holds the Qdrant folder lock.
"""
from __future__ import annotations
import json
import threading

from langchain_core.tools import tool

from kb.search import KB

SNIP = 150          # per-hit text budget — see _cap() on why this is tight
CORPORA = ("k9_reviews", "k9_issues", "k9_sentences", "ap_issues")

# LangGraph's ToolNode runs one turn's tool calls in PARALLEL threads, and
# `KB.qc` lazy-inits without a lock: two threads both see `_qc is None`, both
# construct a client, and Qdrant local mode refuses the second with
# "Storage folder ... already accessed by another instance". kb/ was written
# single-threaded and is a different lane, so the fix lives here: every tool
# body holds this lock, which serialises that lazy init along with everything
# else. Every tool is sub-100ms, so serialising costs nothing measurable.
_LOCK = threading.RLock()
_KB: KB | None = None


def _kb() -> KB:
    global _KB
    if _KB is None:
        with _LOCK:
            if _KB is None:
                _KB = KB()            # cheap: the client itself stays lazy
    return _KB


def close_kb() -> None:
    """Release the Qdrant lock. The CLI calls this on exit."""
    global _KB
    with _LOCK:
        if _KB is not None:
            _KB.close()
            _KB = None


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _note(terms: str) -> dict:
    """Multi-word terms match as PHRASES, and models pass them by accident.

    `polarity("battery drain")` reads 0.87 (adjacent words only, 5 reviews);
    `polarity("battery,drain")` reads 1.46 (either word, 44 reviews) — opposite
    conclusions from one missing comma. Phrases are legitimate here
    ("syncing disabled" is a real 26-review signal), so we cannot just split on
    whitespace. Instead we hand the correction back inline, where the model is
    looking, at the moment it matters.
    """
    multi = [t.strip() for t in terms.split(",") if " " in t.strip()]
    if not multi:
        return {}
    return {"note": f"matched {multi} as exact phrase(s), not as separate words. "
                    f"If you meant any-of, re-call with commas: "
                    f"{','.join(w for t in multi for w in t.split())}"}


def _bare(ref) -> str:
    """Strip our own citation prefix. The prompt tells the model to cite as
    `rev:83c34e81` / `k9#857`, so it naturally feeds those handles straight
    back into a lookup — observed live burning two tool calls before guessing
    the bare id. A citation must round-trip into the tool that resolves it.
    """
    t = str(ref).strip()
    for pre in ("rev:", "sent:", "k9#", "antennapod#", "issue#", "#"):
        if t.lower().startswith(pre):
            return t[len(pre):].strip()
    return t


def _cap(v, default: int, hi: int) -> int:
    """A limit the model cannot blow the token budget with.

    Groq's free tier allows 12,000 tokens/minute and tool results persist in
    the transcript, so one `compare_vocabularies(limit=10)` (3 corpora x 10
    hits) costs ~1.8k tokens on this turn AND every turn after it. Three of
    those in parallel is a 413. The model asks for what it likes; we clamp.
    """
    return max(1, min(_int(v, default), hi))


def _int(v, default: int) -> int:
    """Free-tier models emit "2" where the schema says integer, and Groq
    validates tool calls server-side — a 400 kills the turn before any of this
    code runs. So every numeric parameter is typed `int | str` and squeezed
    back to an int here. Junk falls back to the default rather than raising:
    a slightly wrong limit beats a dead conversation.
    """
    try:
        return int(float(_bare(v)))
    except (TypeError, ValueError):
        return default


def _empty(*sides: dict) -> dict:
    """`kb` labels a null ratio "balanced". Zero matches on both sides is not
    balance, it is NO DATA — and a model reading "balanced" will report it as a
    finding. Observed live: `polarity("syncing issues")` matched 0/1560 and
    0/1086, and the answer claimed developers mention syncing more than users.
    Overriding the label here is cheaper than teaching every model to check n.
    """
    if all(sd.get("n", 0) == 0 for sd in sides):
        return {"reading": "NO DATA — these terms appear nowhere in either "
                           "corpus. The ratio is meaningless. Try other wording, "
                           "and state nothing about this topic."}
    if any(sd.get("n", 0) == 0 for sd in sides):
        return {"reading": "ONE SIDE EMPTY — the ratio is undefined, not "
                           "infinite. Report the raw counts, not a ratio."}
    return {}


def _hits(rows: list[dict]) -> list[dict]:
    out = []
    for h in rows:
        p = h.get("payload", {})
        row = {"cite": h["cite"], "text": (h.get("text") or "")[:SNIP]}
        for k in ("star", "date", "state", "type_label", "days_open", "number"):
            if p.get(k) is not None:
                row[k] = p[k]
        if "score" in h:
            row["score"] = h["score"]
        out.append(row)
    return out


# ----------------------------------------------------------------- semantic
@tool
def search_reviews(query: str, limit: int | str = 5,
                   max_star: int | str = 5) -> str:
    """Semantic search over 1,560 K-9 Mail user reviews (2015-11 to 2017-05).

    Finds reviews by MEANING, so it matches user phrasing you did not type.
    Use it to discover what users complain about. max_star=2 isolates angry
    reviews; max_star=5 (default) searches all of them.
    DISCOVERY ONLY — never quote the number of results as a count. Use
    count_terms for that.
    """
    limit, max_star = _cap(limit, 5, 10), _int(max_star, 5)
    where = {"star": {"lte": max_star}} if max_star < 5 else None
    with _LOCK:
        return _j(_hits(_kb().search(query, "k9_reviews", limit, where)))


@tool
def search_issues(query: str, limit: int | str = 5, state: str = "") -> str:
    """Semantic search over 1,718 K-9 Mail GitHub issues (2015-03 to 2017-12).

    This is the developer side of the corpus — how maintainers describe and
    track the product. state may be "open", "closed", or "" for both.
    DISCOVERY ONLY, same caveat as search_reviews.
    """
    with _LOCK:
        return _j(_hits(_kb().search(query, "k9_issues", _cap(limit, 5, 10),
                                     {"state": state} if state else None)))


@tool
def compare_vocabularies(query: str, limit: int | str = 3) -> str:
    """Run ONE query against reviews, issues and sentences at once.

    The core discovery move. Read the two result sets side by side and ask:
    do users and developers use the SAME WORDS for this? When reviews say
    "battery drains" and issues say "Doze" / "wakelock" / "JobScheduler", that
    vocabulary split is the signal — the same defect, filed under a name no
    user would ever search for. Feed both word sets into polarity() next.
    """
    with _LOCK:
        return _j({name: _hits(rows)
                   for name, rows in _kb().search_all(query, _cap(limit, 3, 5)).items()})


@tool
def related_issues(number: int | str, limit: int | str = 5) -> str:
    """Issues semantically similar to a given issue number. More-like-this."""
    with _LOCK:
        return _j(_hits(_kb().neighbors("k9_issues", _int(number, 0),
                                        _cap(limit, 5, 10))))


# ------------------------------------------------------------------ lexical
@tool
def count_terms(terms: str, corpus: str = "k9_reviews",
                max_star: int | str = 5) -> str:
    """EXACT word-boundary count of terms across a corpus. This is EVIDENCE.

    terms: comma-separated, e.g. "battery,drain,overheat".
    corpus: k9_reviews | k9_issues | k9_sentences | ap_issues.
    Returns n_matched, n_scanned and rate_per_1k plus example citations.
    Every number you state in an answer must come from this tool, polarity,
    or control — never from counting search results yourself.
    """
    if corpus not in CORPORA:
        return _j({"error": f"corpus must be one of {list(CORPORA)}"})
    max_star = _int(max_star, 5)
    where = {"star": {"lte": max_star}} if max_star < 5 and "review" in corpus else None
    with _LOCK:
        r = _kb().lexical(terms, corpus, where, limit=4)
    return _j({k: r[k] for k in ("collection", "terms", "n_matched",
                                 "n_scanned", "rate_per_1k")}
              | _note(terms) | {"examples": _hits(r["matches"])})


@tool
def polarity(terms: str) -> str:
    """THE THESIS METRIC. How much louder are users than the backlog on these terms?

    Compares the term's rate per 1,000 reviews against its rate per 1,000
    issues, restricted to the window both corpora share (aligned — the
    defensible comparison).

      ratio > 1.2  user-led — users raise it more than developers file it
      ratio < 0.83 dev-led  — tracked in a vocabulary users never say

    A misframing gap shows up as a PAIR: symptom words scoring user-led and
    mechanism words scoring dev-led. Run this on both word sets.
    """
    with _LOCK:
        r = _kb().polarity(terms, aligned=True)
    return _j(r | _note(terms) | _empty(r["reviews"], r["issues"]))


@tool
def control(terms: str) -> str:
    """THE FALSIFIER. Same terms against AntennaPod's backlog (unrelated app).

    Run this before claiming any finding is real. A term just as common in an
    unrelated Android app's issues is a platform-wide artefact, not a K-9 gap.
      ratio_k9_over_control > 1.5  k9-specific
      below that                   platform-wide — do NOT report it as a gap
    """
    with _LOCK:
        r = _kb().control(terms)
    return _j(r | _note(terms) | _empty(r["k9_issues"], r["ap_issues"]))


# ------------------------------------------------------------------- lookup
@tool
def get_issue(number: int | str) -> str:
    """Full record for one GitHub issue: title, body, labels, milestone, url,
    and days_open (measured against a frozen 2026-07-31, so an issue still open
    today shows its full age). Long-open `type: enhancement` issues are the
    priority signal — enhancements take a median 970 days to close, bugs 195.
    """
    with _LOCK:
        got = _kb().get("k9_issues", [_int(number, 0)])
    if not got:
        return _j({"error": f"issue {number} not in corpus"})
    p = got[0]["payload"]
    return _j({k: (str(p[k])[:700] if k == "body" else p[k])
               for k in ("number", "title", "body", "state", "created_at",
                         "closed_at", "days_open", "type_label", "labels",
                         "milestone", "comments", "url") if k in p})


@tool
def get_review(review_id: str) -> str:
    """Full text of one review by id (8-char prefix from a `rev:` citation is
    enough). Use it to quote a user verbatim after search_reviews found it."""
    rid = _bare(review_id)
    with _LOCK:
        hit = next((d for d in _kb().get("k9_reviews", [rid]) if d), None)
    if hit is None:                       # citations are 8-char prefixes
        from kb import documents as docs
        hit = next(({"payload": d["payload"]} for d in docs.load("k9_reviews")
                    if d["id"].startswith(rid)), None)
    if hit is None:
        return _j({"error": f"no review matching {review_id!r}"})
    p = hit["payload"]
    return _j({k: p[k] for k in ("review_id", "text", "star", "date") if k in p})


# --------------------------------------------------------------- the findings
# These read data/gaps.json — the deterministic engine's output — and never
# recompute anything. That is the point: on stage the model must not be able to
# re-derive a different confidence for the same gap than the one on the slide.
# The engine decides; the agent explains and cites.
@tool
def top_gaps() -> str:
    """THE ANSWER TO THE BRIEF. The ranked unmet needs the roadmap is missing,
    strongest evidence first, each with confidence, verdict and evidence ids.

    Call this FIRST for any question like "what are the gaps", "what did the
    roadmap miss", "what do users need". Do not rebuild this from searches —
    these numbers are computed deterministically and are the ones being scored.
    """
    from gaps import engine

    res = engine.load()
    if not res:
        return _j({"error": "no data/gaps.json yet — run: make gaps"})
    return _j({"meta": res["meta"], "gaps": [
        {"rank": g["rank"], "need": g["need"], "id": g["id"],
         "confidence": g["confidence"], "verdict": g["verdict"],
         "why_verdict": g["reason"],
         "users_say": g["symptom_terms"], "backlog_says": g["mechanism_terms"],
         "n_reviews": g["metrics"]["n_reviews"],
         "mean_star": g["metrics"]["mean_star"],
         "n_issues": g["metrics"]["n_issues"],
         "pii": g["metrics"]["pii"], "bridge": g["metrics"]["bridge_n"],
         "evidence_ids": [r["cite"] for r in g["evidence"]["reviews"][:6]]
                         + [i["cite"] for i in g["evidence"]["issues"][:4]]}
        for g in res["gaps"]]})


@tool
def why_gap(gap_id: str) -> str:
    """Full arithmetic behind ONE gap: every confidence component, every
    penalty with its cost and reason, the verdict counts, and the evidence
    trace by id. This is what answers "defend that confidence score" and
    "why is this ranked #1" — the breakdown is already computed, quote it.
    """
    from gaps import engine

    res = engine.load()
    if not res:
        return _j({"error": "no data/gaps.json yet — run: make gaps"})
    g = next((x for x in res["gaps"] if x["id"] == _bare(gap_id)), None)
    if not g:
        return _j({"error": f"no gap {gap_id!r}",
                   "available": [x["id"] for x in res["gaps"]]})
    return _j({"rank": g["rank"], "need": g["need"],
               "confidence": g["confidence"], "formula": g["score"]["formula"],
               "evidence_half": g["score"]["E"], "latency_half": g["score"]["L"],
               "penalties": g["score"]["penalties"],
               "verdict": g["verdict"], "why": g["why"], "reason": g["reason"],
               "metrics": {k: g["metrics"][k] for k in
                           ("n_reviews", "prevalence", "mean_star",
                            "star_deficit", "months_hit", "max_share",
                            "n_issues", "n_open", "median_days_open", "epics",
                            "pii", "bridge_n", "control_ratio",
                            "control_reading", "recurrence")},
               "evidence": g["evidence"]})


@tool
def missed_gap(terms: str) -> str:
    """THE ADVERSARIAL TOOL. Answers "here's a gap you missed — why isn't it in
    your output?" for any comma-separated terms.

    Returns exactly one of four honest statuses:
      SURFACED             it IS in the output, at this rank
      CONSIDERED & REJECTED it was scored and dropped — names the component
                            that failed and its confidence
      BELOW THRESHOLD      it is in the corpus at this rate and mean star, but
                            under the support floor — includes real verbatims
      NOT IN CORPUS        users never say it; the issue count is given instead

    Use this whenever someone proposes a topic that is not already a gap.
    """
    from gaps import engine

    with _LOCK:
        return _j(engine.probe(terms))


TOOLS = [top_gaps, why_gap, missed_gap,
         search_reviews, search_issues, compare_vocabularies, related_issues,
         count_terms, polarity, control, get_issue, get_review]
