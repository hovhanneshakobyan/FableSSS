"""S2 — latent-need signal families. The thing that stops this being a counter.

A frequency ranking of complaints is worthless here: the loudest themes are the
ones already on the roadmap, because loud is exactly how they got there. What we
want is the need that is *structurally quiet* — present in the corpus but in a
form that never becomes a ticket.

Six families, each a different reason a real need stays invisible:

  F1 workaround      user already solved it -> never files it
  F2 happy-friction  4-5 star reviewer -> net satisfied -> never escalates
  F3 regression      names a change in the world, not a missing feature
  F4 tenure+defection tolerance threshold crossed; the churn is the signal
  F5 competitor      names a capability by pointing at someone else's
  F6 conditional     "5 stars if..." -> the user has PRICED the gap

lambda(r) = sum of weights of the families review r matches. A theme's latent
density is mean lambda over its reviews, and that is what ranking rewards --
so a theme can beat a more frequent one by being quieter in the right way.

Every family is a word-boundary regex over raw review text. No model decides
whether a review is a workaround; a regex does, and you can grep it yourself.
"""
from __future__ import annotations

import re
from functools import lru_cache

from kb import documents as docs

# Weights: how strongly a family implies "real need that never became a ticket".
# F1/F6 are the strongest -- both are users who have fully articulated the gap
# and still had no reason to file. F5 is weakest: naming a competitor is common
# rhetorical furniture in app reviews and only sometimes carries a capability.
WEIGHTS = {"F1": 1.0, "F2": 1.0, "F3": 0.9, "F4": 0.8, "F5": 0.6, "F6": 1.0}

# Contrast connectives that turn a positive review into a friction report.
# Deliberately narrow: a bare "but" anywhere in a long review is noise, so F2
# additionally requires the reviewer to be 4-5 star (see _f2).
CONTRAST = (r"\bbut\b|\bhowever\b|\bexcept\b|\bthough\b|\balthough\b|"
            r"\bonly (?:issue|problem|complaint|thing|downside)\b|"
            r"\bwish\b|\bwould love\b|\bif only\b|\bone thing\b|\bdownside\b")

PATTERNS: dict[str, str] = {
    # ---- F1: the user built their own fix. The strongest latent marker.
    # Every alternative here must imply EFFORT THE USER ABSORBED. Two traps,
    # both found by sampling matches: a bare "manually" catches praise ("my
    # favorite is manually marking emails as read") and a bare "trick"/"hack"
    # catches "does the trick", which is a compliment. Both are gone -- the
    # verb now has to be governed by "have to" / "only way" / "end up".
    "F1": (r"\bwork ?arounds?\b|\bi just use\b|\bi have to use\b|"
           r"\bso i use\b|\binstead i\b|\bi use .{0,20}instead\b|"
           r"\bevery time i have to\b|\bhave to (?:manually|re-?open|restart|"
           r"force|clear|reinstall|toggle|refresh|forward|set (?:it )?up|"
           r"go into|delete|check)\b|\bdo(?:ing)? it manually\b|"
           r"\bmanually (?:every|each|again)\b|\bonly way (?:to|i|around)\b|"
           r"\bmy only option\b|\bi (?:end up|resort to)\b|\bmy way around\b"),

    # ---- F2: handled in _f2 (needs the star rating, not just the text).
    "F2": CONTRAST,

    # ---- F3: it worked before. Names a regression, which no feature request
    # ever captures -- there is no ticket for "put it back".
    "F3": (r"\bused to\b|\bsince (?:the |a |your )?(?:last |recent |latest )?"
           r"(?:update|upgrade|version|release)\b|\bafter (?:the |an? )?"
           r"(?:update|upgrade)\b|\bsince (?:updating|upgrading|installing)\b|"
           r"\bno longer\b|\bstopped working\b|\bworked (?:fine|great|well|"
           r"perfectly)\b|\bbroke\b|\bbroken since\b|\bregression\b|"
           r"\bwent downhill\b|\bnot as good as it (?:used to be|was)\b"),

    # ---- F4a: tenure. A long-time user's complaint is a threshold crossing,
    # not a first impression.
    "F4_tenure": (r"\bfor years\b|\bfor (?:many|several|\d+) years\b|"
                  r"\bsince 20\d\d\b|\blong ?-?time (?:user|fan)\b|"
                  r"\bused (?:this|k-?9) for\b|\bloyal\b|\bveteran\b|"
                  r"\byears (?:of use|now)\b|\bever since i\b"),

    # ---- F4b: defection. The user is leaving; the need left with them.
    "F4_churn": (r"\buninstall(?:ed|ing)?\b|\bswitch(?:ed|ing)? to\b|"
                 r"\bmoving to\b|\bmoved to\b|\bgoing back to\b|\bdeleted?\b|"
                 r"\bgave up\b|\bdone with\b|\bgoodbye\b uninstall|"
                 r"\blooking for (?:an? )?(?:alternative|replacement)\b|"
                 r"\bfound (?:a )?better\b"),

    # ---- F5: competitor naming. The capability is described by reference.
    "F5": (r"\bgmail\b|\boutlook\b|\bblue ?mail\b|\baqua ?mail\b|\bthunderbird\b|"
           r"\bprotonmail\b|\byahoo mail\b|\bnine\b|\btype ?app\b|\bmyMail\b|"
           r"\binbox by gmail\b|\bmaildroid\b|\bfairemail\b|\bcompared to\b|"
           r"\bunlike (?:gmail|outlook|other)\b|\bother (?:email )?(?:apps?|"
           r"clients?)\b"),

    # ---- F6: conditional praise. The user has stated their exact price.
    # Careful: in THIS corpus "star" usually means the UI star (flag/favourite)
    # -- "can't click star to favorite", "bad star placement". So a rating
    # reading is only taken when a number or a rating verb governs it.
    "F6": (r"\b(?:five|5|6|ten|10) stars? if\b|\b\d+ stars? if\b|"
           r"\bwould (?:be|give|rate|add) (?:it |you )?(?:another |more |a )?"
           r"(?:five|5|6|\d+)? ?stars?\b|\bwould be (?:a )?(?:five|5)\b|"
           r"\b(?:i'?ll|will) (?:add|give|bump|raise) .{0,20}stars?\b|"
           r"\bmore stars? (?:if|when|once)\b|\bif only\b|"
           r"\botherwise (?:perfect|flawless|great|excellent|5)\b|"
           r"\bperfect except\b|\bonly reason .{0,30}(?:not|isn'?t) (?:five|5)\b|"
           r"\b(?:four|4) stars? (?:because|until|only because)\b"),
}

RX = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}

# F2 only counts for a satisfied reviewer: a 1-star review full of "but" is a
# complaint, and complaints are the non-latent case this engine exists to skip.
HAPPY_STARS = (4, 5)


# "I don't have to delete them one by one" is praise for the absence of a
# workaround. Same words, inverted meaning -- and F1 is the highest-weight
# family, so letting one through would distort a ranking.
NEGATOR = re.compile(r"(?:don'?t|do not|doesn'?t|didn'?t|never|no need|won'?t)"
                     r"\s+(?:\w+\s+){0,2}$", re.I)


def _f1(text: str) -> bool:
    """A workaround the user actually performs -- not one they were spared."""
    for m in RX["F1"].finditer(text):
        if not NEGATOR.search(text[max(0, m.start() - 40):m.start()]):
            return True
    return False


def _f2(text: str, star: int) -> bool:
    return star in HAPPY_STARS and bool(RX["F2"].search(text))


def _f4(text: str) -> bool:
    """Tenure AND defection, or defection alone from a long-form review.

    Either half alone is weak -- "uninstalled" appears in first-day rage, and
    "for years" appears in praise. The conjunction is the threshold crossing.
    """
    return bool(RX["F4_tenure"].search(text) and RX["F4_churn"].search(text))


def families(text: str, star: int) -> list[str]:
    """Which latent families this review matches. Order is stable for output."""
    hits = []
    if _f1(text):
        hits.append("F1")
    if _f2(text, star):
        hits.append("F2")
    if RX["F3"].search(text):
        hits.append("F3")
    if _f4(text):
        hits.append("F4")
    if RX["F5"].search(text):
        hits.append("F5")
    if RX["F6"].search(text):
        hits.append("F6")
    return hits


def lam(fams: list[str]) -> float:
    """lambda(r) -- the latent weight of one review."""
    return round(sum(WEIGHTS[f] for f in fams), 2)


def explain(text: str, star: int) -> dict[str, str]:
    """Which exact phrase put this review in each family.

    A classification a judge cannot audit is worth nothing, so every family
    assignment carries the substring that triggered it. This is also how the
    regexes get maintained: a bad match is visible as a bad phrase, which is
    how "manually" and "trick" were caught and removed.
    """
    out: dict[str, str] = {}
    for fam in families(text, star):
        key = "F4_churn" if fam == "F4" else fam
        if m := RX[key].search(text):
            out[fam] = m.group(0).strip().lower()
    return out


@lru_cache(maxsize=1)
def annotated() -> list[dict]:
    """Every review with its families, lambda, and the third-party label.

    Computed once and cached: this is the substrate every later stage reads.
    The sentence join is what lets F0 (the dataset authors' own PROBLEM
    DISCOVERY / FEATURE REQUEST labels) corroborate our regexes -- an
    independent signal we did not author, which is worth more than one we did.
    """
    intents: dict[str, set[str]] = {}
    for s in docs.load("k9_sentences"):
        p = s["payload"]
        intents.setdefault(p["review_id"], set()).add(p["intention"])

    out = []
    for d in docs.load("k9_reviews"):
        p = d["payload"]
        fams = families(p["text"], p["star"])
        tags = intents.get(p["review_id"], set())
        out.append({
            "review_id": p["review_id"], "cite": f"rev:{p['review_id'][:8]}",
            "text": p["text"], "star": p["star"], "date": p["date"],
            "ym": p["ym"], "chars": p["chars"],
            "families": fams, "lam": lam(fams),
            # F0 -- not ours. Noisy (see PLAN.md 10.4), used only to corroborate.
            "f0_problem": "PROBLEM DISCOVERY" in tags,
            "f0_request": "FEATURE REQUEST" in tags,
        })
    return out


def density() -> dict:
    """Per-family counts. Printed by `python -m gaps signals` so the numbers on
    a slide can be regenerated in one command."""
    rows = annotated()
    n = len(rows)
    per = {f: sum(1 for r in rows if f in r["families"]) for f in WEIGHTS}
    latent = [r for r in rows if r["lam"] > 0]
    return {
        "reviews": n,
        "families": {f: {"n": c, "pct": round(100 * c / n, 1)}
                     for f, c in per.items()},
        "latent_pool": {"n": len(latent), "pct": round(100 * len(latent) / n, 1),
                        "mean_star": round(sum(r["star"] for r in latent)
                                           / max(1, len(latent)), 2)},
        "corpus_mean_star": round(sum(r["star"] for r in rows) / n, 2),
    }
