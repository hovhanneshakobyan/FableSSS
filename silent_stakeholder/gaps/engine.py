"""S6/S7 — the run. Candidates in, ranked gaps + rejected candidates out.

Two artefacts, and the second one matters as much as the first:

  data/gaps.json        the 3-5 findings, ranked, each with its full arithmetic
  data/candidates.json  EVERY candidate considered, including the rejects, with
                        the component that failed and the ids it was built from

The rejects file is how "here's a gap you missed" gets answered on stage. Either
it is in there with a score and a failing component -- considered and rejected,
here is why -- or it genuinely was not considered, and saying so plainly beats
improvising. A system that cannot enumerate what it ruled out is a demo.
"""
from __future__ import annotations

import json
import os
import re

from gaps import measure, score, themes
from gaps.signals import annotated

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data")

# Floors a candidate must clear to be measured at all. Deliberately low: the
# point is to REJECT loudly with a reason, not to quietly never consider things.
MIN_REVIEWS = 8
MIN_CONFIDENCE = 25
TOP_N = 5


def _expand(term: str) -> list[str]:
    """A theme is a term plus the phrasings users actually use for it.

    Kept small and lexical on purpose. Aggressive expansion is how a gap
    silently becomes a different gap between the count and the claim.
    """
    extra = {
        "battery": ["battery", "drain", "draining", "power"],
        "syncing disabled": ["syncing disabled", "sync disabled"],
        "ads": ["ads", "advert", "advertising"],
        "notifications": ["notification", "notifications", "notify"],
        "multiple accounts": ["multiple accounts", "several accounts"],
        "security": ["security", "encrypt", "encryption", "pgp"],
        "swipe": ["swipe", "swiping", "gesture"],
        "zoom": ["zoom", "pinch", "font size", "text size"],
        "interface": ["interface", "layout", "design"],
        "search": ["search", "searching", "find email"],
        "attachment": ["attachment", "attachments", "attach"],
        "folder": ["folder", "folders", "subfolder"],
    }
    return extra.get(term, [term])


def candidates(n_latent: int = 14, n_polarity: int = 14) -> list[dict]:
    """Both discovery routes, deduplicated, ready to measure."""
    out, seen = [], []
    for s in themes.seeds(n_latent) + themes.polarity_seeds(n_polarity):
        term = s["term"]
        if themes._subsumed(term, seen):
            continue
        seen.append(term)
        out.append({"id": re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-"),
                    "label": term, "route": s["route"],
                    "symptom_terms": _expand(term), "discovery": s})
    return out


def _sample(sym: list[str]) -> str:
    """A real review in the user's own words — the query for the bridge."""
    pat = measure.rx(sym)
    hit = [r for r in annotated() if pat.search(r["text"].lower())]
    hit.sort(key=lambda r: (-r["lam"], r["star"]))
    return hit[0]["text"][:300] if hit else ""


# A need stated in the user's terms, as the brief requires. This QUOTES rather
# than paraphrases, on purpose: an LLM summary of what users want is the exact
# step where a finding drifts from its evidence, and "in the user's terms" is
# satisfied most literally by using the user's terms.
#
# Which sentence, though, is a real choice. Ranking by lambda picks the most
# LATENT review, which is not the same as the clearest statement of need -- it
# offered "Very good  Been using it for years for my yahoo Gmail and Hotmail
# accounts" as the Hotmail need, which is praise. So selection runs over the
# 4,224 sentences the dataset authors labelled by intention, preferring
# PROBLEM DISCOVERY and FEATURE REQUEST. Those labels are third-party and noisy
# (PLAN.md 10.4), which is fine here: they are choosing a quote to display, not
# producing a number, and the quote is shown with its id so it can be checked.
WANT = ("FEATURE REQUEST", "PROBLEM DISCOVERY")


def _need(sym: list[str], label: str) -> dict:
    from kb import documents as docs

    pat = measure.rx(sym)
    cands = []
    for s in docs.load("k9_sentences"):
        p = s["payload"]
        text = p["text"].strip()
        if not (30 <= len(text) <= 190) or not pat.search(text.lower()):
            continue
        if p["intention"] not in WANT:
            continue
        # A feature request states the need most directly; after that, prefer
        # the unhappier reviewer, then the longer (more specific) sentence.
        cands.append((WANT.index(p["intention"]), p.get("star") or 5,
                      -len(text), text, p["review_id"]))

    if cands:
        _, star, _, text, rid = min(cands)
        return {"need": text, "quote": text, "quote_cite": f"rev:{rid[:8]}",
                "quote_star": star}

    # No labelled sentence mentions this theme — fall back to the raw review.
    hit = [r for r in annotated() if pat.search(r["text"].lower())]
    if not hit:
        return {"need": label, "quote": None, "quote_cite": None}
    hit.sort(key=lambda r: (-r["lam"], r["star"]))
    top = hit[0]
    return {"need": top["text"][:190].strip(), "quote": top["text"][:190].strip(),
            "quote_cite": top["cite"], "quote_star": top["star"]}


def run(top_n: int = TOP_N, verbose: bool = True) -> dict:
    """The whole pipeline. Deterministic: same corpus in, same JSON out."""
    scored, rejected = [], []

    for cand in candidates():
        cand.update(_need(cand["symptom_terms"], cand["label"]))
        cand["mechanism"] = measure.mechanism_terms(cand["symptom_terms"],
                                                    _sample(cand["symptom_terms"]))
        m = measure.measure(cand)
        if m.get("dead") or m["n_reviews"] < MIN_REVIEWS:
            rejected.append({**_slim(cand), "failed": "support",
                             "detail": f"{m.get('n_reviews', 0)} reviews "
                                       f"< floor {MIN_REVIEWS}"})
            continue

        g = score.assemble(cand, m)
        if verbose:
            print(f"  {g['confidence']:>3}  {g['verdict']:<18} {g['label']:<22}"
                  f" n={m['n_reviews']:<4} PII={m['pii']} bridge={m['bridge_n']}")
        if g["confidence"] < MIN_CONFIDENCE:
            rejected.append({**_slim(cand), "failed": _weakest(g),
                             "confidence": g["confidence"],
                             "detail": f"confidence {g['confidence']} "
                                       f"< floor {MIN_CONFIDENCE}",
                             "components": g["score"]})
            continue
        scored.append(g)

    scored.sort(key=score.rank_key)
    kept, extra = scored[:top_n], scored[top_n:]
    rejected += [{**_slim(g), "failed": "rank",
                  "confidence": g["confidence"],
                  "detail": f"scored below the top {top_n}"} for g in extra]

    score.apply_caps(kept)
    for i, g in enumerate(kept, 1):
        g["rank"] = i

    return {"gaps": kept, "rejected": rejected,
            "meta": {"as_of": "2026-07-31", "reviews": 1560, "issues": 1718,
                     "candidates_considered": len(scored) + len(rejected),
                     "surfaced": len(kept)}}


def _weakest(g: dict) -> str:
    """The component that cost this candidate the most — the honest answer to
    "why did you drop it?"."""
    if g["score"]["penalties"]:
        return max(g["score"]["penalties"], key=lambda p: p["cost"])["code"]
    e = g["score"]["E"]
    return min(("support", "dispersion", "friction", "quality"),
               key=lambda k: e[k])


def _slim(c: dict) -> dict:
    return {"id": c["id"], "label": c["label"], "route": c["route"],
            "symptom_terms": c.get("symptom_terms", []),
            "mechanism_terms": [x["term"] for x in c.get("mechanism", [])]
            or c.get("mechanism_terms", [])}


def write(result: dict) -> tuple[str, str]:
    a = os.path.join(OUT, "gaps.json")
    b = os.path.join(OUT, "candidates.json")
    with open(a, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
    with open(b, "w", encoding="utf-8") as fh:
        json.dump({"rejected": result["rejected"], "meta": result["meta"]},
                  fh, indent=1, ensure_ascii=False)
    return a, b


def load() -> dict | None:
    """Read the last run. The UI and the defense console both go through here."""
    path = os.path.join(OUT, "gaps.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------- defense
def probe(terms: str) -> dict:
    """"Here's a gap you missed" — answered in four ways, all of them honest.

    SURFACED             it is in the output, at this rank
    CONSIDERED&REJECTED  it was scored and dropped, by this component
    BELOW THRESHOLD      it is in the corpus at this rate, under the floor
    NOT IN CORPUS        users do not say this; here is the issue count instead
    """
    want = [t.strip().lower() for t in terms.split(",") if t.strip()]
    res = load()
    if res:
        for g in res["gaps"]:
            if any(w in " ".join(g["symptom_terms"] + [g["label"]]).lower()
                   for w in want):
                return {"status": "SURFACED", "rank": g["rank"], "gap": g["id"],
                        "need": g["need"], "confidence": g["confidence"],
                        "verdict": g["verdict"]}
        for r in res["rejected"]:
            if any(w in " ".join(r.get("symptom_terms", []) + [r["label"]]).lower()
                   for w in want):
                return {"status": "CONSIDERED & REJECTED", "candidate": r["id"],
                        "failed_component": r["failed"], "detail": r["detail"],
                        "confidence": r.get("confidence")}

    k = measure.kb()
    rev = k.lexical(want, "k9_reviews", limit=10)
    iss = k.lexical(want, "k9_issues", limit=5)
    if not rev["n_matched"]:
        return {"status": "NOT IN CORPUS", "terms": want,
                "reviews": 0, "issues": iss["n_matched"],
                "reading": f"0 user mentions against {iss['n_matched']} issues"
                           " — that is the inverse of a gap"}

    pat = measure.rx(want)
    hit = [r for r in annotated() if pat.search(r["text"].lower())]
    mean = round(sum(r["star"] for r in hit) / len(hit), 2)
    return {"status": "BELOW THRESHOLD", "terms": want,
            "n_reviews": rev["n_matched"], "of": 1560,
            "pct": round(100 * rev["n_matched"] / 1560, 2),
            "n_issues": iss["n_matched"],
            "mean_star": mean, "corpus_mean_star": 3.43,
            "floor": MIN_REVIEWS,
            "verbatims": [{"cite": r["cite"], "star": r["star"],
                           "text": r["text"][:200]} for r in hit[:10]]}
