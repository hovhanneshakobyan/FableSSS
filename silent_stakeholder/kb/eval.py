"""KB layer 4 — retrieval evaluation. Ground truth with no labelling.

    .venv/bin/python -m kb eval [--n 150]

Two probes, both self-supervised — the corpora already know the right answer:

  sentence -> review   every sentence came from exactly one review. Ask for the
                       sentence, expect its parent. Measures whether short,
                       noisy user language retrieves the right document.

  body -> issue        take a phrase out of an issue body and ask for it back.
                       Run twice: once with text from the first 600 chars, once
                       with text from beyond it. The gap between those two
                       numbers is exactly what truncation costs.

Recall is the only metric here on purpose. This index answers "did the right
document come back at all", and a ranking metric would hide the failure mode
that actually bit: whole regions of a corpus being unreachable.

Baseline, 2026-07-31, chunked index (n=150):
  sentence -> review      @1 48.7  @5 63.0  @10 69.3
  body inside 600 chars   @1 57.9  @5 79.3  @10 83.4
  body beyond 600 chars   @1 71.7  @5 82.8  @10 89.0   (was 12.4 / 25.5 / 35.9)
"""
from __future__ import annotations
import random, re

from kb import documents as D
from kb.search import KB

KS = (1, 5, 10)
SEED = 11                       # fixed: two runs must be comparable


def _recall(kb: KB, queries: list[str], gold: list, collection: str,
            key) -> dict:
    got = {k: 0 for k in KS}
    for q, g in zip(queries, gold):
        hits = kb.search(q, collection, limit=max(KS))
        ids = [key(h) for h in hits]
        for k in KS:
            got[k] += g in ids[:k]
    return {f"recall@{k}": round(100 * v / len(gold), 1) for k, v in got.items()}


def _phrase(text: str) -> str | None:
    """A quotable sentence, with code fences and markdown noise stripped."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[#*>`\[\]_\r]", " ", text)
    parts = [p.strip() for p in re.split(r"[.\n]", text) if len(p.strip()) > 60]
    return parts[0][:220] if parts else None


def sentence_to_review(kb: KB, n: int) -> dict:
    rows = [(d["text"], d["payload"]["review_id"])
            for d in D.load("k9_sentences") if len(d["text"]) > 25]
    rows = random.Random(SEED).sample(rows, min(n, len(rows)))
    return _recall(kb, [r[0] for r in rows], [r[1] for r in rows],
                   "k9_reviews", lambda h: h["payload"]["review_id"])


def body_to_issue(kb: KB, n: int) -> tuple[dict, dict, int]:
    """Same issues, two query sources: inside vs beyond the old 600-char cut."""
    inside, beyond, gold = [], [], []
    for d in D.load("k9_issues"):
        body = d["payload"]["body"] or ""
        if len(body) <= 1400:
            continue
        a, z = _phrase(body[:600]), _phrase(body[700:2000])
        if a and z:
            inside.append(a); beyond.append(z); gold.append(d["id"])
    m = min(n, len(gold))
    key = lambda h: h["payload"]["number"]
    return (_recall(kb, inside[:m], gold[:m], "k9_issues", key),
            _recall(kb, beyond[:m], gold[:m], "k9_issues", key), m)


def run(n: int = 150) -> dict:
    with KB() as kb:
        s = sentence_to_review(kb, n)
        inside, beyond, m = body_to_issue(kb, n)
    return {"n_sentence_queries": n, "n_issue_queries": m,
            "sentence_to_review": s,
            "body_inside_600": inside, "body_beyond_600": beyond}


def report(res: dict) -> None:
    fmt = lambda d: "  ".join(f"{k.split('@')[1]:>3}:{v:>5}" for k, v in d.items())
    print(f"  sentence -> review      (n={res['n_sentence_queries']})  "
          f"{fmt(res['sentence_to_review'])}")
    print(f"  body inside 600 chars   (n={res['n_issue_queries']})  "
          f"{fmt(res['body_inside_600'])}")
    print(f"  body beyond 600 chars   (n={res['n_issue_queries']})  "
          f"{fmt(res['body_beyond_600'])}")
    print("  (columns are recall@1 / @5 / @10, percent)")
