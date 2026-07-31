"""LANE A — raw JSON -> SQLite. Deterministic, idempotent, offline.

    python3 pipeline/a_ingest.py                    # K-9 -> data/gap.db
    python3 pipeline/a_ingest.py --app antennapod   # negative control -> data/gap_ap.db

Nothing downstream may read data/raw/ directly. This is the only door.
AS_OF is frozen: staleness must not drift between the slide and the stage.
"""
from __future__ import annotations
import argparse, datetime, json, os, sqlite3, sys

AS_OF = "2026-07-31"          # FROZEN. Never datetime.now().
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")

APPS = {
    "k9": {
        "db": "data/gap.db", "repo": "thunderbird/thunderbird-android",
        "reviews": "k9_reviews.json", "sentences": "k9_sentences.json",
        "issues": "k9_issues_all.json",
        "expect": {"reviews": 1560, "sentences": 4224, "issues": 1718},
    },
    "antennapod": {
        "db": "data/gap_ap.db", "repo": "AntennaPod/AntennaPod",
        "reviews": None, "sentences": None,
        "issues": "ap_issues.json",
        "expect": {"reviews": 0, "sentences": 0, "issues": 1000},
    },
}


def _raw(name: str):
    with open(os.path.join(RAW, name), encoding="utf-8") as fh:
        return json.load(fh)


def _days(start: str, end: str) -> int:
    return (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days


# ------------------------------------------------------------------ loaders
def load_reviews(db: sqlite3.Connection, app: dict) -> int:
    """k9_reviews.json -> reviews, with star_band / ym derived inline."""
    if not app["reviews"]:
        return 0
    rows = _raw(app["reviews"])
    db.executemany(
        "INSERT OR REPLACE INTO reviews "
        "(id, text, date_iso, star, chars, star_band, ym, version_id) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(r["id"], r["text"], r["date"], int(r["star"]), int(r["chars"]),
          "low" if r["star"] <= 2 else "mid" if r["star"] == 3 else "high",
          r["date"][:7], int(r["version_id"])) for r in rows])
    return len(rows)


def load_sentences(db: sqlite3.Connection, app: dict) -> int:
    """Third-party intention labels. Noisy — corroboration, never gospel."""
    if not app["sentences"]:
        return 0
    rows = _raw(app["sentences"])
    db.executemany(
        "INSERT INTO sentences (review_id, text, intention, topic) VALUES (?,?,?,?)",
        [(s["review_id"], s["text"], s["intention"], s["topic"]) for s in rows])
    return len(rows)


def load_issues(db: sqlite3.Connection, app: dict) -> int:
    """Raw GitHub JSON -> issues. days_open measured against frozen AS_OF."""
    rows = _raw(app["issues"])
    out = []
    for i in rows:
        title, body = i.get("title") or "", i.get("body") or ""
        labels = [l["name"] for l in i.get("labels") or []]
        created, closed = i["created_at"][:10], (i.get("closed_at") or "")[:10] or None
        reason = i.get("state_reason")
        out.append((
            i["number"], title, body, (title + " " + body).strip(),
            i["state"], created, closed,
            _days(created, closed or AS_OF),
            next((l.split(": ", 1)[1] for l in labels if l.startswith("type: ")), None),
            (i.get("milestone") or {}).get("title"),
            i.get("html_url", ""), i.get("comments", 0),
            1 if i["state"] == "open" else 0,          # is_stale_open
            reason, json.dumps(labels), created[:7],
            1 if any(l == "status: needs information" for l in labels) else 0,
            1 if reason == "not_planned" else 0,
        ))
    db.executemany(
        "INSERT OR REPLACE INTO issues "
        "(number,title,body,text_concat,state,created_at,closed_at,days_open,"
        " type_label,milestone,html_url,comments,is_stale_open,state_reason,"
        " labels_json,ym,is_needs_info,is_not_planned) "
        "VALUES (" + ",".join("?" * 18) + ")", out)
    return len(out)


# Columns added after the first schema.sql shipped. Applied additively so a
# re-ingest never drops reviews.llm_* (Lane C's batch labels cost an hour).
MIGRATIONS = {
    "issues": [("state_reason", "TEXT"), ("labels_json", "TEXT"), ("ym", "TEXT"),
               ("is_needs_info", "INTEGER DEFAULT 0"),
               ("is_not_planned", "INTEGER DEFAULT 0")],
}


def migrate(db: sqlite3.Connection) -> list[str]:
    applied = []
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                applied.append(f"{table}.{name}")
    return applied


def build_fts(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO reviews_fts(reviews_fts) VALUES('rebuild')")
    db.execute("INSERT INTO issues_fts(issues_fts) VALUES('rebuild')")


def manifest(db: sqlite3.Connection, app_key: str, app: dict, counts: dict) -> None:
    db.executemany("INSERT OR REPLACE INTO run_manifest (key,value) VALUES (?,?)",
                   [("as_of", AS_OF), ("app", app_key), ("repo", app["repo"]),
                    ("ingested_schema", "v2"),
                    *[(f"n_{k}", str(v)) for k, v in counts.items()]])


# ------------------------------------------------------------------ driver
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="k9", choices=sorted(APPS))
    ap.add_argument("--db", default=None, help="override target db path")
    args = ap.parse_args()
    app = APPS[args.app]
    path = os.path.join(HERE, args.db or app["db"])

    db = sqlite3.connect(path)
    db.executescript(open(os.path.join(HERE, "schema.sql"), encoding="utf-8").read())
    migrated = migrate(db)
    for t in ("reviews", "sentences", "issues"):
        db.execute(f"DELETE FROM {t}")                 # idempotent re-runs

    counts = {"reviews": load_reviews(db, app),
              "sentences": load_sentences(db, app),
              "issues": load_issues(db, app)}
    build_fts(db)
    manifest(db, args.app, app, counts)
    db.commit()

    bad = {k: (v, app["expect"][k]) for k, v in counts.items() if v != app["expect"][k]}
    for k, (got, want) in bad.items():
        print(f"FAIL {k}: got {got}, expected {want}", file=sys.stderr)
    if bad:
        return 1

    q = lambda s, *a: db.execute(s, a).fetchone()[0]
    print(f"[{args.app}] {path}")
    print(f"  reviews   {counts['reviews']:>5}  "
          + (f"{q('SELECT MIN(date_iso) FROM reviews')} -> "
             f"{q('SELECT MAX(date_iso) FROM reviews')}  "
             f"mean* {q('SELECT ROUND(AVG(star),2) FROM reviews')}"
             if counts["reviews"] else "(none — issues-only control)"))
    print(f"  sentences {counts['sentences']:>5}")
    print(f"  issues    {counts['issues']:>5}  "
          f"{q('SELECT MIN(created_at) FROM issues')} -> "
          f"{q('SELECT MAX(created_at) FROM issues')}  "
          f"open {q('SELECT COUNT(*) FROM issues WHERE state=?', 'open')}")
    print(f"  AS_OF     {AS_OF} (frozen)")
    if migrated:
        print(f"  migrated  {', '.join(migrated)}")
    print("  asserts   OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
