"""Recompute every load-bearing number in PLAN.md / CLAUDE.md against gap.db.

PLAN.md §0 says "recompute before quoting; do not trust prose." This makes that
a command. Run it before anything goes on a slide.

    make verify        # exit 0 = every documented claim reproduces
"""
from __future__ import annotations
import os, sqlite3, statistics, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = sqlite3.connect(os.path.join(HERE, "data", "gap.db"))
one = lambda s, *a: db.execute(s, a).fetchone()[0]

CHECKS: list[tuple[str, object, object]] = []


def check(label, got, want):
    CHECKS.append((label, got, want))


# ---- corpus shape (PLAN.md §0)
check("reviews", one("SELECT COUNT(*) FROM reviews"), 1560)
check("reviews window", (one("SELECT MIN(date_iso) FROM reviews"),
                         one("SELECT MAX(date_iso) FROM reviews")),
      ("2015-11-29", "2017-05-02"))
check("mean star", one("SELECT ROUND(AVG(star),2) FROM reviews"), 3.43)
check("star hist", dict(db.execute("SELECT star,COUNT(*) FROM reviews GROUP BY star")),
      {1: 277, 2: 205, 3: 223, 4: 282, 5: 573})
check("issues", one("SELECT COUNT(*) FROM issues"), 1718)
check("issues open", one("SELECT COUNT(*) FROM issues WHERE state='open'"), 166)
check("issues closed", one("SELECT COUNT(*) FROM issues WHERE state='closed'"), 1552)
check("milestoned", one("SELECT COUNT(*) FROM issues WHERE milestone IS NOT NULL"), 259)
check("sentences", one("SELECT COUNT(*) FROM sentences"), 4224)
check("PROBLEM DISCOVERY",
      one("SELECT COUNT(*) FROM sentences WHERE intention='PROBLEM DISCOVERY'"), 508)
check("FEATURE REQUEST",
      one("SELECT COUNT(*) FROM sentences WHERE intention='FEATURE REQUEST'"), 209)

# ---- the priority signal (CLAUDE.md "Key facts")
for t, med, opn in (("enhancement", 970, 136), ("bug", 195, 21)):
    d = [r[0] for r in db.execute(
        "SELECT days_open FROM issues WHERE type_label=? AND closed_at IS NOT NULL", (t,))]
    check(f"{t} median days", round(statistics.median(d)), med)
    check(f"{t} still open",
          one("SELECT COUNT(*) FROM issues WHERE type_label=? AND state='open'", t), opn)

# ---- gap #1 core evidence: issue #857
check("#857 created", one("SELECT created_at FROM issues WHERE number=857"), "2015-10-23")
check("#857 closed", one("SELECT closed_at FROM issues WHERE number=857"), "2021-06-30")
check("#857 days", one("SELECT days_open FROM issues WHERE number=857"), 2077)
check("#857 milestone", one("SELECT milestone FROM issues WHERE number=857"),
      "Mail synchronization")
check("#857 type", one("SELECT type_label FROM issues WHERE number=857"), "enhancement")

# ---- happy-but-broken pool (PLAN.md §0). 120 SENTENCES, but only 104 distinct
# reviews — say "104 reviewers" on stage, never "120 users".
check("happy-but-broken sent", one(
    "SELECT COUNT(*) FROM sentences s JOIN reviews r ON r.id=s.review_id "
    "WHERE s.intention='PROBLEM DISCOVERY' AND r.star>=4"), 120)
check("happy-but-broken revs", one(
    "SELECT COUNT(DISTINCT s.review_id) FROM sentences s JOIN reviews r ON r.id=s.review_id "
    "WHERE s.intention='PROBLEM DISCOVERY' AND r.star>=4"), 104)

# ---- frozen AS_OF must never drift
check("AS_OF frozen", one("SELECT value FROM run_manifest WHERE key='as_of'"), "2026-07-31")

fails = [c for c in CHECKS if c[1] != c[2]]
for label, got, want in CHECKS:
    print(f"{'ok  ' if got == want else 'FAIL'}  {label:<22} {got}"
          + ("" if got == want else f"   (doc says {want})"))
print(f"\n{len(CHECKS) - len(fails)}/{len(CHECKS)} claims reproduce")
sys.exit(1 if fails else 0)
