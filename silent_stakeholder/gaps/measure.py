"""S4 — measurement. Every number a gap will ever show comes from this file.

The contract with the discovery layer (themes.py) is one-directional and strict:
discovery may PROPOSE any term it likes, from keyness or from a vector
neighbourhood; nothing it proposes is believed until it has been counted here
with a word-boundary regex over data/raw/. A proposed term that counts to
nothing is dropped, not softened.

That is what lets the mechanism bridge use embeddings safely. Qdrant is the only
component that can cross "battery drain" -> "doze/wakelock/jobscheduler" -- the
two phrasings share no words, so no keyword method can find the pair -- but
Qdrant's similarity score never enters a metric. It proposes the vocabulary;
kb.lexical does the arithmetic.

Everything here is deterministic and offline. Same corpus in, same numbers out.
"""
from __future__ import annotations

import math
import os
import re
import statistics
from functools import lru_cache

from gaps import themes
from gaps.signals import annotated
from kb import documents as docs

CORPUS_MEAN_STAR = 3.43          # recomputed in signals.density(), not trusted prose
WINDOW_MONTHS = 18               # 2015-11 -> 2017-05, the review window

_KB = None


def rx(terms: list[str]) -> re.Pattern:
    """Word-boundary OR-regex, phrases matched literally.

    Deliberately the same construction as kb.search._rx: a count produced here
    and a count produced by the KB tools the agent calls on stage must be the
    same number, or the demo contradicts itself in public.
    """
    return re.compile("|".join(
        rf"\b{re.escape(t.lower())}\b" if " " not in t else re.escape(t.lower())
        for t in terms))


def kb():
    """One KB for the whole run. Qdrant local mode allows a single client."""
    global _KB
    if _KB is None:
        from kb import KB
        _KB = KB()
    return _KB


_SNAP = None


def _vector_kb():
    """A KB whose vector index we can definitely open.

    Qdrant local mode is single-writer, and the Streamlit UI holds that lock for
    as long as it is running. Without this, `make gaps` during a demo silently
    drops to the keyword fallback and writes WEAKER mechanism terms over a good
    gaps.json -- a quiet quality regression at the worst possible moment.
    So on contention we snapshot the index to a temp directory and read that.
    Vectors are immutable here (kb/index.py rebuilds, never mutates), so a copy
    is the same index, and the running UI never notices.
    """
    global _SNAP
    try:
        kb().qc                                   # cheap: opens or raises
        return kb()
    except Exception:
        if _SNAP is None:
            import shutil
            import tempfile

            from kb import KB
            from kb.index import QDRANT

            dst = os.path.join(tempfile.mkdtemp(prefix="gaps-qdrant-"), "q")
            shutil.copytree(QDRANT, dst)
            for junk in (".lock",):
                p = os.path.join(dst, junk)
                if os.path.exists(p):
                    os.remove(p)
            _SNAP = KB(path=dst)
        return _SNAP


def close() -> None:
    global _KB, _SNAP
    if _KB is not None:
        _KB.close()
        _KB = None
    if _SNAP is not None:
        _SNAP.close()
        _SNAP = None


# --------------------------------------------------------------- mechanism
# How many nearest issues to read the developer vocabulary out of. Small on
# purpose: past ~15 the neighbourhood stops being about the query and the
# proposed terms drift into generic backlog boilerplate ("build", "gradle").
NEIGHBOURS = 12
MAX_MECHANISM = 6

# What makes a term "the developer's word for it" is measured on the USER side,
# not as a ratio. Measured against the known answer:
#
#   term          df_rev  df_iss  ratio        term        df_rev df_iss ratio
#   doze               5      10   1.8         screen          25    142   5.2
#   wakelock           0       1   inf         seems           30    112   3.4
#   jobscheduler       0       1   inf         folder          37    251   6.2
#   idle               2      22  10.0         imap            50    929  16.9
#
# A ratio test ranks `screen` (5.2x) above `doze` (1.8x) and would have thrown
# away the one mechanism this corpus is known to contain -- doze looks weak by
# ratio only because so few users have the word at all, which is precisely the
# property being looked for. So the gate is absolute rarity on the user side:
# a mechanism term is one users DO NOT HAVE. Boilerplate fails it on volume.
MAX_REVIEW_DF = 6          # <=0.4% of 1,560 reviews
MIN_ISSUE_DF = 4           # and really present in the backlog

# ...and SPECIFIC to a defect. K-9's bug template ("Expected behavior / Actual
# behavior / Tell us what happens") defeats every user-side test on its own:
# "actual" sits in 809 of 1,718 issues and 2 of 1,560 reviews, which scores as
# perfect developer vocabulary while meaning nothing at all. A term present
# across more than 5% of the backlog is furniture, not a mechanism.
MAX_ISSUE_DF = int(0.05 * themes.ISSUES_N)


def _neighbourhood(symptom: list[str], sample: str) -> tuple[list[int], str]:
    """Issue numbers to read developer vocabulary out of, and how we got them.

    Vectors are preferred -- they are the only thing that can reach an issue
    sharing NO words with the user's phrasing, which is the whole point of a
    framing gap. But Qdrant local mode is single-writer, and during a demo the
    Streamlit UI legitimately holds that lock. Falling over because a teammate's
    app is open is not acceptable, so there is a keyword fallback:

      lexical anchor -- issues that literally mention a symptom term. Weaker
      (it only finds mechanisms that CO-OCCUR with the user's word at least
      once) but it is exactly the population the bridge gate audits anyway, so
      a MISUNDERSTOOD verdict never depended on the vector path.

    Which route ran is recorded on the gap. A finding that changes with the
    retrieval mode is a finding you have to disclose.
    """
    try:
        query = f"{' '.join(symptom)} {sample}".strip()[:400]
        hits = _vector_kb().search(query, "k9_issues", limit=NEIGHBOURS)
        return [h["payload"]["number"] for h in hits], "vector"
    except Exception:                       # lock held, or no index built
        pat = rx(symptom)
        anchored = [d["payload"] for d in docs.load("k9_issues")
                    if pat.search(f"{d['payload']['title']} "
                                  f"{d['payload']['body']}".lower())]
        anchored.sort(key=lambda p: -p["comments"])       # most-discussed first
        return [p["number"] for p in anchored[:NEIGHBOURS * 2]], "lexical"


def mechanism_terms(symptom: list[str], sample: str = "") -> list[dict]:
    """Developer vocabulary for a user-described symptom. PROPOSAL ONLY.

    Read the issues nearest the user's phrasing and take the terms that
    distinguish them from the backlog at large. Keep only terms that are
    DEV-LED -- said more per-1k in issues than in reviews -- because a term both
    sides already use is shared vocabulary, and shared vocabulary is precisely
    what a framing gap does not have.
    """
    numbers, how = _neighbourhood(symptom, sample)
    if not numbers:
        return []

    want = set(numbers)
    near, rest = [], []
    for d in docs.load("k9_issues"):
        p = d["payload"]
        row = {"text": f"{p['title']} {p['body']}"}
        (near if p["number"] in want else rest).append(row)

    sym = set(symptom)
    rev_df, iss_df = _review_df(), themes._issue_df()

    out = []
    for term, z, df in themes.keyness(near, rest, min_df=3, prior=50.0):
        if term in sym or any(term in s or s in term for s in sym):
            continue
        r_rate = themes.PER * rev_df[term] / themes.REVIEWS_N
        i_rate = themes.PER * iss_df[term] / themes.ISSUES_N
        # Users must not have this word, developers must. See MAX_REVIEW_DF.
        if not MIN_ISSUE_DF <= iss_df[term] <= MAX_ISSUE_DF:
            continue
        if rev_df[term] > MAX_REVIEW_DF:
            continue
        if i_rate <= r_rate:                      # dev-led at minimum
            continue
        out.append({"term": term, "z": z, "df_issues": iss_df[term],
                    "df_reviews": rev_df[term], "found_by": how})
        if len(out) >= MAX_MECHANISM:
            break
    return out


@lru_cache(maxsize=1)
def _review_df():
    return themes._df([{"text": r["text"]} for r in annotated()])


# ------------------------------------------------------------------ metrics
def _months(dates: list[str]) -> dict:
    """Dispersion: a need is sustained, an event is a spike."""
    if not dates:
        return {"months_hit": 0, "max_share": 1.0, "dispersion": 0.0, "by_month": {}}
    by: dict[str, int] = {}
    for d in dates:
        by[d[:7]] = by.get(d[:7], 0) + 1
    top = max(by.values()) / len(dates)
    disp = (len(by) / WINDOW_MONTHS) * (1 - top)
    return {"months_hit": len(by), "max_share": round(top, 3),
            "dispersion": round(min(1.0, max(0.0, disp)), 3),
            "by_month": dict(sorted(by.items()))}


def _linked_issues(terms: list[str]) -> list[dict]:
    """Backlog items that match the gap's vocabulary — the roadmap's response."""
    res = kb().lexical(terms, "k9_issues", limit=0)
    pat = rx(terms)
    out = []
    for d in docs.load("k9_issues"):
        p = d["payload"]
        if pat.search(f"{p['title']} {p['body']}".lower()):
            out.append(p)
    assert len(out) == res["n_matched"], "lexical and local scan disagree"
    return out


def _bridge(sym: list[str], mech: list[str]) -> list[dict]:
    """Documents where BOTH vocabularies appear — the link, witnessed.

    Without this a framing claim is an assertion: "users mean X when they say
    Y". A bridge document is a case where one author said both, so the mapping
    is observed rather than assumed. PLAN.md gates MISUNDERSTOOD on >= 3.
    """
    if not mech:
        return []
    rx_s, rx_m = rx(sym), rx(mech)

    out = []
    for name, key in (("k9_issues", "number"), ("k9_reviews", "review_id")):
        for d in docs.load(name):
            p = d["payload"]
            hay = (f"{p.get('title', '')} {p.get('body', '')} "
                   f"{p.get('text', '')}").lower()
            if rx_s.search(hay) and rx_m.search(hay):
                out.append({"cite": f"k9#{p['number']}" if key == "number"
                            else f"rev:{p['review_id'][:8]}",
                            "corpus": name,
                            "symptom": rx_s.search(hay).group(0),
                            "mechanism": rx_m.search(hay).group(0)})
    return out


def _median_close(issues: list[dict]) -> str | None:
    closed = sorted(i["closed_at"] for i in issues if i.get("closed_at"))
    return closed[len(closed) // 2] if closed else None


def measure(cand: dict) -> dict:
    """Everything measurable about one candidate. No verdict, no score yet."""
    sym = cand["symptom_terms"]

    # --- user side -------------------------------------------------------
    rows = annotated()
    pat = rx(sym)
    hit = [r for r in rows if pat.search(r["text"].lower())]
    n = len(hit)
    if not n:
        return {"n_reviews": 0, "dead": True}

    stars = [r["star"] for r in hit]
    mean_star = round(statistics.mean(stars), 2)
    latent = [r for r in hit if r["lam"] > 0]
    happy_friction = [r for r in hit if "F2" in r["families"]]
    long_form = [r for r in hit if r["chars"] >= 120]
    labelled = [r for r in hit if r["f0_problem"] or r["f0_request"]]

    # --- mechanism + backlog side ---------------------------------------
    mech = [m["term"] for m in cand.get("mechanism", [])]
    linked = _linked_issues(sym + mech)
    pol_s = kb().polarity(sym, aligned=True)
    pol_m = kb().polarity(mech, aligned=True) if mech else None
    ctrl = kb().control(sym)

    ps = pol_s["ratio_user_over_dev"]
    pm = pol_m["ratio_user_over_dev"] if pol_m else None
    # PII: how far apart the two vocabularies sit. Guarded -- a mechanism with
    # zero issue matches gives pm=None, and log2(x/0) is not a finding.
    pii = round(math.log2(ps / pm), 2) if (ps and pm and pm > 0) else None

    bridge = _bridge(sym, mech)
    med = _median_close(linked)
    after = [r for r in hit if med and r["date"] > med]

    open_iss = [i for i in linked if i["state"] == "open"]
    epics = sorted({i["milestone"] for i in linked if i.get("milestone")})

    return {
        "dead": False,
        # user side
        "n_reviews": n,
        "prevalence": round(100 * n / len(rows), 2),
        "mean_star": mean_star,
        "star_deficit": round(mean_star - CORPUS_MEAN_STAR, 2),
        "latent_n": len(latent),
        "latent_share": round(len(latent) / n, 3),
        "mean_lambda": round(statistics.mean([r["lam"] for r in hit]), 3),
        "happy_friction_share": round(len(happy_friction) / n, 3),
        "long_form_share": round(len(long_form) / n, 3),
        "f0_share": round(len(labelled) / n, 3),
        **_months([r["date"] for r in hit]),
        # backlog side
        "n_issues": len(linked),
        "n_open": len(open_iss),
        "stale_frac": round(len(open_iss) / len(linked), 3) if linked else 0.0,
        "not_planned_frac": round(sum(i["is_not_planned"] for i in linked)
                                  / len(linked), 3) if linked else 0.0,
        "needs_info_frac": round(sum(i["is_needs_info"] for i in linked)
                                 / len(linked), 3) if linked else 0.0,
        "enhancement_frac": round(sum(i.get("type_label") == "enhancement"
                                      for i in linked) / len(linked), 3)
        if linked else 0.0,
        "median_days_open": statistics.median([i["days_open"] for i in linked])
        if linked else None,
        "epics": epics,
        "median_closed_at": med,
        "recurrence": round(len(after) / n, 3) if med else 0.0,
        # framing
        "polarity_symptom": ps,
        "polarity_mechanism": pm,
        "pii": pii,
        "pii_norm": round(min(1.0, max(0.0, pii / 4)), 3) if pii else 0.0,
        "bridge_n": len(bridge),
        "bridge": bridge[:12],
        "control_ratio": ctrl["ratio_k9_over_control"],
        "control_reading": ctrl["reading"],
        # evidence — real ids, capped for payload size
        "evidence_reviews": [
            {"cite": r["cite"], "star": r["star"], "date": r["date"],
             "families": r["families"], "lam": r["lam"],
             "text": r["text"][:280]}
            for r in sorted(hit, key=lambda r: (-r["lam"], r["star"]))[:12]],
        "evidence_issues": [
            {"cite": f"k9#{i['number']}", "title": i["title"][:110],
             "state": i["state"], "created_at": i["created_at"],
             "closed_at": i["closed_at"], "days_open": i["days_open"],
             "type": i.get("type_label"), "milestone": i.get("milestone"),
             "comments": i["comments"]}
            for i in sorted(linked, key=lambda i: -i["days_open"])[:10]],
    }
