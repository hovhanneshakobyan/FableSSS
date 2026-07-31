"""LANE B (discovery) — gap.db -> Qdrant, three collections.

    .venv/bin/python pipeline/c_embed.py            # build all three
    .venv/bin/python pipeline/c_embed.py --probe "battery drains overnight"

DISCOVERY ONLY. Vector hits propose candidates; they are never shown as proof.
The number on the slide always comes from keyword counting in tools.py.

Reads from gap.db, never from data/raw/ — a_ingest.py is the only door.
Qdrant runs in local mode: a folder, no server, no process to die on stage.
"""
from __future__ import annotations
import argparse, os, sqlite3, sys

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "data", "gap.db")
QDRANT = os.path.join(HERE, "data", "qdrant")
MODEL = "BAAI/bge-small-en-v1.5"     # 384-dim, 67MB, offline after first fetch
DIM = 384

# Issue bodies run to thousands of chars; bge truncates at 512 tokens anyway.
BODY_CHARS = 600

COLLECTIONS = ("k9_reviews", "k9_issues", "k9_sentences")


# ---------------------------------------------------------------- sources
def fetch_reviews(db) -> tuple[list, list, list]:
    rows = db.execute(
        "SELECT id, text, star, date_iso, ym, star_band, chars, version_id "
        "FROM reviews ORDER BY id").fetchall()
    ids = [r[0] for r in rows]                      # UUIDs — valid Qdrant ids
    texts = [r[1] for r in rows]
    payload = [{"review_id": r[0], "text": r[1], "star": r[2], "date": r[3],
                "ym": r[4], "star_band": r[5], "chars": r[6], "version_id": r[7]}
               for r in rows]
    return ids, texts, payload


def fetch_issues(db) -> tuple[list, list, list]:
    rows = db.execute(
        "SELECT number, title, body, state, created_at, closed_at, days_open, "
        "type_label, milestone, comments, html_url FROM issues ORDER BY number").fetchall()
    ids = [r[0] for r in rows]                      # issue number == point id
    texts = [f"{r[1]} {(r[2] or '')[:BODY_CHARS]}".strip() for r in rows]
    payload = [{"number": r[0], "title": r[1], "text": t, "state": r[3],
                "created_at": r[4], "closed_at": r[5], "days_open": r[6],
                "type_label": r[7], "milestone": r[8], "comments": r[9], "url": r[10]}
               for r, t in zip(rows, texts)]
    return ids, texts, payload


def fetch_sentences(db) -> tuple[list, list, list]:
    rows = db.execute(
        "SELECT s.rowid, s.review_id, s.text, s.intention, s.topic, r.star, r.date_iso "
        "FROM sentences s LEFT JOIN reviews r ON r.id = s.review_id "
        "ORDER BY s.rowid").fetchall()
    ids = [r[0] for r in rows]
    texts = [r[2] for r in rows]
    payload = [{"sentence_id": r[0], "review_id": r[1], "text": r[2],
                "intention": r[3], "topic": r[4], "star": r[5], "date": r[6]}
               for r in rows]
    return ids, texts, payload


SOURCES = {"k9_reviews": fetch_reviews, "k9_issues": fetch_issues,
           "k9_sentences": fetch_sentences}


# ---------------------------------------------------------------- indexing
def build(client: QdrantClient, embedder: TextEmbedding, db, name: str) -> int:
    ids, texts, payload = SOURCES[name](db)
    if not ids:
        print(f"  {name:<14} SKIP (no rows — run make ingest first)")
        return 0

    if client.collection_exists(name):               # idempotent rebuilds
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE))

    vectors = [v.tolist() for v in embedder.embed(texts, batch_size=256)]
    for lo in range(0, len(ids), 512):
        hi = lo + 512
        client.upsert(collection_name=name, points=models.Batch(
            ids=ids[lo:hi], vectors=vectors[lo:hi], payloads=payload[lo:hi]))

    n = client.count(name).count
    print(f"  {name:<14} {n:>5} vectors  dim={DIM}")
    return n


def probe(client: QdrantClient, embedder: TextEmbedding, query: str) -> None:
    """Sanity check: does semantic search actually bridge the vocabularies?"""
    qv = next(iter(embedder.embed([query]))).tolist()
    for name in COLLECTIONS:
        print(f"\n--- {name} ~ {query!r}")
        for h in client.query_points(name, query=qv, limit=3).points:
            p = h.payload
            tag = (f"#{p['number']}" if "number" in p
                   else p.get("review_id", "")[:8])
            print(f"  {h.score:.3f}  {tag:<10} {p['text'][:88].strip()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", metavar="TEXT", help="semantic search smoke test")
    ap.add_argument("--only", choices=COLLECTIONS, help="rebuild one collection")
    args = ap.parse_args()

    if not os.path.exists(DB):
        print("data/gap.db missing — run: make ingest", file=sys.stderr)
        return 1

    embedder = TextEmbedding(MODEL)
    client = QdrantClient(path=QDRANT)               # local mode: a folder
    db = sqlite3.connect(DB)

    if args.probe:
        probe(client, embedder, args.probe)
        return 0

    print(f"[qdrant] {QDRANT}  model={MODEL}")
    total = sum(build(client, embedder, db, n)
                for n in ([args.only] if args.only else COLLECTIONS))
    print(f"  {'total':<14} {total:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
