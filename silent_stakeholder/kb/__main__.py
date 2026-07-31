"""KB command line. Run everything through .venv/bin/python -m kb.

    -m kb stats
    -m kb build [--only k9_issues] [--rebuild]
    -m kb search "battery drains overnight" [--in k9_issues] [--where star<=2]
    -m kb lexical battery,drain,overheat --in k9_reviews
    -m kb polarity battery,drain,overheat
    -m kb get k9_issues 857 970

--where accepts key=value (comma-separated value = any-of) and key<=/>=value.
"""
from __future__ import annotations
import argparse, json, sys

from kb.documents import COLLECTIONS, SOURCES
from kb.search import KB


def parse_where(clauses: list[str] | None) -> dict:
    """'star<=2' -> {'star': {'lte': 2}};  'state=open,closed' -> list match."""
    out: dict = {}
    for c in clauses or []:
        for op, key in ((">=", "gte"), ("<=", "lte"), (">", "gt"), ("<", "lt")):
            if op in c:
                field, _, raw = c.partition(op)
                out.setdefault(field.strip(), {})[key] = _cast(raw)
                break
        else:
            if "=" not in c:
                raise SystemExit(f"bad --where {c!r}: need key=value or key<=value")
            field, _, raw = c.partition("=")
            vals = [_cast(v) for v in raw.split(",")]
            out[field.strip()] = vals if len(vals) > 1 else vals[0]
    return out


def _cast(s: str):
    s = s.strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return {"true": True, "false": False, "null": None}.get(s.lower(), s)


def show_hits(hits: list[dict]) -> None:
    for h in hits:
        score = f"{h['score']:.3f}  " if "score" in h else ""
        print(f"  {score}{h['cite']:<12} {h.get('text', '')[:96]}")
    if not hits:
        print("  (no hits)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="embed data/raw into data/qdrant")
    b.add_argument("--only", choices=COLLECTIONS)
    b.add_argument("--rebuild", action="store_true", help="drop and re-embed")

    sub.add_parser("stats", help="documents vs vectors, per collection")

    e = sub.add_parser("eval", help="retrieval recall against known answers")
    e.add_argument("--n", type=int, default=150, help="queries per probe")

    s = sub.add_parser("search", help="semantic search (discovery)")
    s.add_argument("query")
    s.add_argument("--in", dest="coll", choices=COLLECTIONS, help="default: all")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--where", action="append")

    l = sub.add_parser("lexical", help="exact term counting (evidence)")
    l.add_argument("terms", help="comma-separated")
    l.add_argument("--in", dest="coll", default="k9_reviews", choices=sorted(SOURCES))
    l.add_argument("--limit", type=int, default=10)
    l.add_argument("--where", action="append")

    p = sub.add_parser("polarity", help="user rate vs backlog rate for terms")
    p.add_argument("terms", help="comma-separated")
    p.add_argument("--aligned", action="store_true",
                   help="restrict issues to the window reviews cover")

    c = sub.add_parser("control", help="K-9 backlog vs AntennaPod, same terms")
    c.add_argument("terms", help="comma-separated")

    g = sub.add_parser("get", help="fetch documents by id")
    g.add_argument("collection", choices=COLLECTIONS)
    g.add_argument("ids", nargs="+")

    a = ap.parse_args(argv)

    if a.cmd == "build":
        from kb.index import build_all
        build_all(a.only, a.rebuild)
        return 0

    if a.cmd == "eval":                 # opens its own KB, then closes it
        from kb import eval as ev
        res = ev.run(a.n)
        print(json.dumps(res, indent=2)) if a.json else ev.report(res)
        return 0

    with KB() as kb:                    # local mode holds a lock — always close
        return dispatch(a, kb)


def dispatch(a, kb: KB) -> int:
    dump = lambda o: print(json.dumps(o, indent=2, ensure_ascii=False, default=str))

    if a.cmd == "stats":
        st = kb.stats()
        if a.json:
            dump(st)
        else:
            for name, v in st.items():
                if v["vectors"] is None:
                    print(f"  {name:<14} {v['documents']:>5} docs  "
                          f"{'—':>5} vectors  raw-only (control)")
                    continue
                flag = "ok" if v["in_sync"] else "STALE — run: -m kb build --rebuild"
                print(f"  {name:<14} {v['documents']:>5} docs  "
                      f"{v['vectors']:>5} vectors  {flag}")
        return 0 if all(v["in_sync"] for v in st.values()) else 1

    if a.cmd == "search":
        where = parse_where(a.where)
        if a.coll:
            res = kb.search(a.query, a.coll, a.limit, where)
            dump(res) if a.json else show_hits(res)
        else:
            res = kb.search_all(a.query, a.limit, where)
            if a.json:
                dump(res)
            else:
                for name, hits in res.items():
                    print(f"\n--- {name} ~ {a.query!r}")
                    show_hits(hits)
        return 0

    if a.cmd == "lexical":
        res = kb.lexical(a.terms, a.coll, parse_where(a.where), a.limit)
        if a.json:
            dump(res)
        else:
            print(f"  {res['n_matched']}/{res['n_scanned']} documents  "
                  f"({res['rate_per_1k']} per 1k)")
            show_hits(res["matches"])
        return 0

    if a.cmd == "polarity":
        res = kb.polarity(a.terms, aligned=a.aligned)
        if a.json:
            dump(res)
        else:
            r, i = res["reviews"], res["issues"]
            print(f"  reviews  {r['n']:>4}/{r['of']}  {r['per_1k']:>7} per 1k")
            print(f"  issues   {i['n']:>4}/{i['of']}  {i['per_1k']:>7} per 1k")
            print(f"  ratio    {res['ratio_user_over_dev']}x  ({res['reading']})")
            print(f"  window   {res['window']}")
        return 0

    if a.cmd == "control":
        res = kb.control(a.terms)
        if a.json:
            dump(res)
        else:
            k, c = res["k9_issues"], res["ap_issues"]
            print(f"  k9        {k['n']:>4}/{k['of']}  {k['per_1k']:>7} per 1k")
            print(f"  control   {c['n']:>4}/{c['of']}  {c['per_1k']:>7} per 1k")
            print(f"  ratio     {res['ratio_k9_over_control']}x  ({res['reading']})")
        return 0

    if a.cmd == "get":
        ids = [int(i) if i.isdigit() else i for i in a.ids]
        res = kb.get(a.collection, ids)
        if a.json:
            dump(res)
        else:
            for d in res:
                p = d["payload"]
                print(f"\n  {d['cite']}  {p.get('title') or p.get('text', '')[:80]}")
                for k in ("state", "type_label", "days_open", "milestone", "comments",
                          "star", "date", "intention", "topic", "url"):
                    if p.get(k) is not None:
                        print(f"    {k:<12} {p[k]}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
