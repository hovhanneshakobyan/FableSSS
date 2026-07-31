"""KB layer 2 — documents -> Qdrant. Local mode: a folder, not a server.

    .venv/bin/python -m kb build              # all three collections
    .venv/bin/python -m kb build --only k9_issues

Rebuilds are idempotent and deterministic: same raw files in, same vectors out.
An existing collection is left alone unless --rebuild is passed, because a
half-finished re-embed on stage is worse than a stale one.
"""
from __future__ import annotations
import os, warnings

from kb.documents import COLLECTIONS, index_docs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDRANT = os.path.join(HERE, "data", "qdrant")
MODEL = "BAAI/bge-small-en-v1.5"     # 384-dim, 67MB, offline after first fetch
DIM = 384
BATCH = 512

# Fields worth an index: everything the search API exposes as a filter.
INDEXED = {
    "star": "integer", "star_band": "keyword", "ym": "keyword", "date": "keyword",
    "state": "keyword", "type_label": "keyword", "milestone": "keyword",
    "days_open": "integer", "comments": "integer", "labels": "keyword",
    "intention": "keyword", "topic": "keyword", "app": "keyword",
    "source": "keyword", "review_id": "keyword", "number": "integer",
    "chunk": "integer", "created_at": "keyword",
}


def client(path: str = QDRANT):
    from qdrant_client import QdrantClient
    return QdrantClient(path=path)


def embedder(model: str = MODEL):
    from fastembed import TextEmbedding
    return TextEmbedding(model)


def build(qc, emb, name: str, rebuild: bool = False) -> int:
    from qdrant_client import models

    if qc.collection_exists(name):
        if not rebuild:
            n = qc.count(name).count
            print(f"  {name:<14} {n:>5} kept (pass --rebuild to re-embed)")
            return n
        qc.delete_collection(name)

    docs = index_docs(name)
    qc.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE))

    vectors = [v.tolist() for v in emb.embed([d["text"] for d in docs], batch_size=256)]
    for lo in range(0, len(docs), BATCH):
        chunk = docs[lo:lo + BATCH]
        qc.upsert(collection_name=name, points=models.Batch(
            ids=[d["id"] for d in chunk],
            vectors=vectors[lo:lo + BATCH],
            payloads=[d["payload"] for d in chunk]))

    # No-op in local mode (it filters by scan and says so, loudly) — declared
    # anyway so pointing QDRANT at a server needs no code change.
    present = set(docs[0]["payload"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for field, schema in INDEXED.items():
            if field in present:
                try:
                    qc.create_payload_index(name, field_name=field, field_schema=schema)
                except Exception:
                    pass

    n = qc.count(name).count
    print(f"  {name:<14} {n:>5} vectors  dim={DIM}")
    return n


def build_all(only: str | None = None, rebuild: bool = False) -> int:
    qc, emb = client(), embedder()
    print(f"[qdrant] {QDRANT}  model={MODEL}")
    total = sum(build(qc, emb, n, rebuild)
                for n in ([only] if only else COLLECTIONS))
    print(f"  {'total':<14} {total:>5}")
    return total
