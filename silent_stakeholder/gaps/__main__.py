"""CLI for the gap engine.

    .venv/bin/python -m gaps run          # full pipeline -> data/gaps.json
    .venv/bin/python -m gaps show         # print the last run
    .venv/bin/python -m gaps why <id>     # one gap's full arithmetic
    .venv/bin/python -m gaps probe <t,t>  # "here's a gap you missed"
    .venv/bin/python -m gaps signals      # latent family densities
"""
from __future__ import annotations

import argparse
import json
import sys

from gaps import engine, measure

BAR = "─" * 78


def _fmt(g: dict) -> str:
    s, m = g["score"], g["metrics"]
    out = [BAR,
           f"#{g['rank']}  {g['need']}",
           f"    {g['confidence']}% confident   ·   {g['verdict']}   ·   "
           f"found by: {g['route']} route",
           "",
           f"    WHY THIS CONFIDENCE   {s['formula']}",
           f"      evidence  E={s['E']['E']}  support={s['E']['support']} "
           f"dispersion={s['E']['dispersion']} friction={s['E']['friction']} "
           f"quality={s['E']['quality']}",
           f"      latency   L={s['L']['L']}  framing={s['L']['pii_norm']} "
           f"recurrence={s['L']['recurrence']} mechanism={s['L']['mechanism']} "
           f"no-epic={s['L']['epic_absence']}"]
    for p in s["penalties"]:
        out.append(f"      −{p['cost']:<3} {p['code']}: {p['why']}")
    out += ["",
            f"    VERDICT  {g['reason']}",
            f"      {g['why']}",
            "",
            f"    USER SIDE   {m['n_reviews']} reviews ({m['prevalence']}% of "
            f"1,560) · mean {m['mean_star']}★ vs 3.43 corpus "
            f"(deficit {m['star_deficit']}) · {m['months_hit']}/18 months",
            f"    BACKLOG     {m['n_issues']} issues · {m['n_open']} still open "
            f"· median {m['median_days_open']}d · epics: "
            f"{', '.join(m['epics']) if m['epics'] else 'NONE'}",
            f"    FRAMING     users say {g['symptom_terms']}",
            f"                backlog says {g['mechanism_terms'] or '—'}",
            f"                PII={m['pii']} · bridge={m['bridge_n']} docs · "
            f"control={m['control_ratio']}x ({m['control_reading']})",
            "",
            "    EVIDENCE TRACE"]
    for r in g["evidence"]["reviews"][:5]:
        out.append(f"      {r['cite']}  {r['star']}★ {r['date']} "
                   f"{'/'.join(r['families']) or '—':<10} {r['text'][:96]}")
    for i in g["evidence"]["issues"][:3]:
        out.append(f"      {i['cite']:<10} {i['state']:<6} {i['days_open']:>5}d "
                   f"{i['title'][:70]}")
    for b in g["evidence"]["bridge"][:3]:
        out.append(f"      {b['cite']:<10} BRIDGE  "
                   f"'{b['symptom']}' + '{b['mechanism']}'")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(prog="gaps")
    ap.add_argument("cmd", choices=["run", "show", "why", "probe", "signals"])
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--top", type=int, default=engine.TOP_N)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        if a.cmd == "signals":
            from gaps.signals import density
            print(json.dumps(density(), indent=2))
            return 0

        if a.cmd == "run":
            print("scoring candidates…")
            res = engine.run(top_n=a.top)
            p1, p2 = engine.write(res)
            print(f"\n{BAR}\nwrote {p1}\n      {p2}")
            print(f"{res['meta']['candidates_considered']} candidates "
                  f"considered · {len(res['gaps'])} surfaced\n")
            for g in res["gaps"]:
                print(_fmt(g))
            return 0

        res = engine.load()
        if res is None:
            print("no data/gaps.json — run:  .venv/bin/python -m gaps run",
                  file=sys.stderr)
            return 1

        if a.cmd == "show":
            if a.json:
                print(json.dumps(res, indent=1))
            else:
                for g in res["gaps"]:
                    print(_fmt(g))
            return 0

        if a.cmd == "why":
            g = next((x for x in res["gaps"] if x["id"] == a.arg), None)
            if not g:
                print(f"no gap '{a.arg}'. have: "
                      f"{[x['id'] for x in res['gaps']]}", file=sys.stderr)
                return 1
            print(_fmt(g) if not a.json else json.dumps(g, indent=1))
            return 0

        if a.cmd == "probe":
            print(json.dumps(engine.probe(a.arg), indent=1))
            return 0
    finally:
        measure.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
