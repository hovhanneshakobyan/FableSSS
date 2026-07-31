"""S5 — confidence, verdict, rank. Every number here is auditable arithmetic.

The brief demands a CALIBRATED confidence: 90%-sure and 55%-sure must differ,
and the number must be justifiable out loud. So confidence is not a model's
opinion and not a vibe. It is a weighted sum of six measured quantities minus
explicit penalties, and every gap ships the component breakdown that produced
it. "Why 71 and not 85?" is answerable by pointing at the row that lost points.

Two independent halves, because they fail independently:

  E  EVIDENCE   — is the signal really there?      support, spread, pain, quality
  L  LATENCY    — is the roadmap really missing it? framing, recurrence, epics

A gap can be loud and well-served (high E, low L -> not a gap) or a hunch about
a real blind spot (low E, high L -> not provable). Only both together is a
finding, which is why the weights are near-even (0.55/0.45) and why neither
half can be compensated by the other.
"""
from __future__ import annotations

import math

# PLAN.md 6. Weights sum to 1.0 within each half.
W_E, W_L = 0.55, 0.45
CAP_MISUNDERSTOOD = 2


def _support(n: int) -> float:
    """Diminishing returns on volume: 100 reviews is not 10x the proof of 10.

    ln-scaled so a gap cannot win on frequency alone -- which is exactly the
    summarizer behaviour the brief penalises.
    """
    return min(1.0, math.log1p(n) / math.log(101))


def evidence(m: dict) -> dict:
    """E — is the signal really in the corpus?"""
    support = _support(m["n_reviews"])
    dispersion = m["dispersion"]
    # Friction is a MAX, not a sum: a gap hurts either by dragging the rating
    # down OR by showing up in otherwise-happy reviews. Adding them would
    # double-count one phenomenon and let a mild gap look severe.
    friction = max(min(1.0, -m["star_deficit"] / 1.0),
                   min(1.0, m["happy_friction_share"] / 0.40))
    quality = 0.5 * m["long_form_share"] + 0.5 * m["f0_share"]
    return {"support": round(support, 3), "dispersion": round(dispersion, 3),
            "friction": round(friction, 3), "quality": round(quality, 3),
            "E": round(0.30 * support + 0.20 * dispersion +
                       0.25 * friction + 0.25 * quality, 4)}


def latency(m: dict) -> dict:
    """L — is the roadmap really missing it?"""
    pii = m["pii_norm"]
    recurrence = m["recurrence"]
    # A mechanism you can name is falsifiable; one you cannot is a story.
    mechanism = 1.0 if m["bridge_n"] >= 3 and m["pii"] else \
                0.5 if m["polarity_mechanism"] is not None else 0.0
    epic_absence = 0.0 if m["epics"] else 1.0
    return {"pii_norm": round(pii, 3), "recurrence": round(recurrence, 3),
            "mechanism": mechanism, "epic_absence": epic_absence,
            "L": round(0.35 * pii + 0.25 * recurrence +
                       0.25 * mechanism + 0.15 * epic_absence, 4)}


def penalties(m: dict) -> list[dict]:
    """Named, priced deductions. Each one is a sentence you can say on stage."""
    out = []
    if m["max_share"] > 0.35:
        out.append({"code": "burst", "cost": 15,
                    "why": f"{m['max_share']:.0%} of evidence lands in one "
                           "month — that is an event, not a sustained need"})
    if m["n_reviews"] < 12:
        out.append({"code": "thin", "cost": 12,
                    "why": f"only {m['n_reviews']} reviews; the trace is too "
                           "short to defend against sampling"})
    if m["control_reading"] == "platform-wide":
        out.append({"code": "control", "cost": 10,
                    "why": f"AntennaPod's backlog carries these terms at a "
                           f"similar rate ({m['control_ratio']}x) — partly a "
                           "platform artefact, not purely a K-9 gap"})
    if m["bridge_n"] < 3 and m["pii"]:
        out.append({"code": "unwitnessed", "cost": 8,
                    "why": f"only {m['bridge_n']} documents use both "
                           "vocabularies; the link is inferred, not observed"})
    if m["months_hit"] <= 3:
        out.append({"code": "narrow", "cost": 8,
                    "why": f"present in only {m['months_hit']} of 18 months"})
    return out


def confidence(m: dict) -> dict:
    """Calibrated 5–95. Ships its own arithmetic."""
    e, l = evidence(m), latency(m)
    pen = penalties(m)
    raw = 100 * (W_E * e["E"] + W_L * l["L"])
    total = round(raw) - sum(p["cost"] for p in pen)
    return {"confidence": max(5, min(95, total)),
            "raw": round(raw, 1), "E": e, "L": l, "penalties": pen,
            "formula": f"round(100 * ({W_E}*E={e['E']} + {W_L}*L={l['L']})) "
                       f"- {sum(p['cost'] for p in pen)} penalties"}


def verdict(m: dict) -> dict:
    """IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD, first match wins.

    The counts that produced the label travel with it. A verdict a judge cannot
    recompute from the printed numbers is not a verdict, it is a label.
    """
    n_iss, n_rev = m["n_issues"], m["n_reviews"]
    why = (f"|issues|={n_iss}, |reviews|={n_rev}, epics={len(m['epics'])}, "
           f"stale={m['n_open']}/{n_iss}, PII={m['pii']}, bridge={m['bridge_n']}")

    # MISUNDERSTOOD is gated hardest: it is the strongest claim (the team IS
    # working on it, under a name the user never uses) and the easiest to fake.
    if (m["pii"] or 0) >= 1.0 and m["bridge_n"] >= 3 and n_iss > 0:
        return {"verdict": "MISUNDERSTOOD", "why": why,
                "reason": f"the backlog engages this ({n_iss} issues) but in a "
                          f"different vocabulary: PII={m['pii']} with "
                          f"{m['bridge_n']} documents witnessing both framings"}
    if n_iss == 0 or (n_iss <= 2 and n_rev >= 40):
        return {"verdict": "IGNORED", "why": why,
                "reason": f"{n_rev} reviews raise it; the backlog answers with "
                          f"{n_iss} issues"}
    if m["not_planned_frac"] >= 0.30 or m["needs_info_frac"] >= 0.40:
        return {"verdict": "IGNORED", "why": why,
                "reason": f"the backlog closes these without acting: "
                          f"not_planned={m['not_planned_frac']:.0%}, "
                          f"needs_info={m['needs_info_frac']:.0%}"}
    return {"verdict": "UNDER-PRIORITIZED", "why": why,
            "reason": f"tracked but slow: {m['n_open']}/{n_iss} still open, "
                      f"median {m['median_days_open']} days, "
                      f"{m['enhancement_frac']:.0%} labelled enhancement "
                      f"(median 970 days to close in this repo)"}


def rank_key(g: dict) -> tuple:
    """Ranked by STRENGTH OF EVIDENCE, as the brief asks — not by confidence.

    Confidence already subtracts penalties for things that make a gap hard to
    defend; ranking on it again would double-count them and push a well-evidenced
    but heavily-caveated finding below a thin, tidy one.
    """
    return (-(0.50 * g["confidence"] / 100 + 0.25 * g["score"]["E"]["E"]
              + 0.15 * g["score"]["L"]["L"]
              + 0.10 * min(1.0, g["metrics"]["n_reviews"] / 60)),)


def assemble(cand: dict, m: dict) -> dict:
    """One measured candidate -> one scored, ranked-ready gap."""
    sc = confidence(m)
    vd = verdict(m)
    return {"id": cand["id"], "need": cand.get("need") or cand["label"],
            "quote": cand.get("quote"), "quote_cite": cand.get("quote_cite"),
            "quote_star": cand.get("quote_star"),
            "label": cand["label"], "route": cand["route"],
            "symptom_terms": cand["symptom_terms"],
            "mechanism_terms": [x["term"] for x in cand.get("mechanism", [])],
            "confidence": sc["confidence"], "score": sc,
            **vd, "metrics": m,
            "evidence": {"reviews": m["evidence_reviews"],
                         "issues": m["evidence_issues"],
                         "bridge": m["bridge"]}}


def apply_caps(gaps: list[dict]) -> list[dict]:
    """At most 2 MISUNDERSTOOD. More than that means the gate is too loose.

    Demoted gaps keep their evidence and say they were demoted, so the cap is
    visible rather than silently reshaping the output.
    """
    seen = 0
    for g in gaps:
        if g["verdict"] != "MISUNDERSTOOD":
            continue
        seen += 1
        if seen > CAP_MISUNDERSTOOD:
            g["verdict"] = "UNDER-PRIORITIZED"
            g["reason"] = (f"[demoted: only the {CAP_MISUNDERSTOOD} strongest "
                           f"framing gaps are reported as MISUNDERSTOOD] "
                           + g["reason"])
    return gaps
