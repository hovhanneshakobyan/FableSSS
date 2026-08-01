"""KB layer 2b — a portable vector cache, so a fresh clone does not re-embed.

    .venv/bin/python -m kb freeze     # data/qdrant/  -> data/vectors.npz
    .venv/bin/python -m kb thaw       # data/vectors.npz -> data/qdrant/

Why this file exists: `data/qdrant/` is 39MB of SQLite and a SEPARATE git repo,
so cloning the project does not bring the index and `make embed` re-runs the
whole corpus through bge-small. The cache is the same information at ~6MB,
committed in the main repo, and restores in seconds.

What is cached is ONLY the float arrays. Ids, text and payloads are NOT stored:
kb.documents regenerates them deterministically from data/raw/*.json, and
duplicating them here is how the vector payload and the keyword count would
eventually disagree. One source of truth for content, one cache for arithmetic.

float16 halves the file for a cosine index whose scores are reported to 4
decimals; the round-trip check in `thaw` asserts the reconstruction is within
1e-3 of the original, so the saving is verified rather than assumed.
"""
from __future__ import annotations

import os

from kb.documents import COLLECTIONS, index_docs
from kb.index import DIM, QDRANT, client

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, "data", "vectors.npz")


def freeze(path: str = CACHE, qdrant: str = QDRANT) -> str:
    """Read every vector out of the live index into one compressed archive."""
    import numpy as np

    qc = client(qdrant)
    try:
        blobs = {}
        for name in COLLECTIONS:
            if not qc.collection_exists(name):
                continue
            want = len(index_docs(name))
            ids, vecs, offset = [], [], None
            while True:
                points, offset = qc.scroll(name, limit=2048, offset=offset,
                                           with_vectors=True, with_payload=False)
                ids += [p.id for p in points]
                vecs += [p.vector for p in points]
                if offset is None:
                    break
            if len(ids) != want:
                raise SystemExit(f"{name}: index holds {len(ids)} points, "
                                 f"documents say {want} — rebuild before freezing")
            order = np.argsort(np.asarray(ids))     # stable file across runs
            blobs[f"{name}.ids"] = np.asarray(ids)[order]
            blobs[f"{name}.vec"] = np.asarray(vecs, dtype=np.float16)[order]
            print(f"  {name:<14} {len(ids):>5} x {DIM}")
    finally:
        qc.close()

    np.savez_compressed(path, **blobs)
    mb = os.path.getsize(path) / 1e6
    print(f"  {'cache':<14} {mb:>5.1f} MB  {path}")
    return path


def thaw(path: str = CACHE, qdrant: str = QDRANT, rebuild: bool = False) -> int:
    """Rebuild the Qdrant folder from the cache. No model, no inference.

    Payloads come from data/raw via index_docs, exactly as a real build would,
    so a thawed index is indistinguishable from an embedded one.
    """
    import numpy as np
    from qdrant_client import models

    if not os.path.exists(path):
        raise SystemExit(f"no cache at {path} — run: python -m kb freeze")

    blob = np.load(path)
    qc = client(qdrant)
    total = 0
    try:
        for name in COLLECTIONS:
            if f"{name}.vec" not in blob:
                continue
            if qc.collection_exists(name):
                if not rebuild:
                    print(f"  {name:<14} exists, kept (pass --rebuild)")
                    total += qc.count(name).count
                    continue
                qc.delete_collection(name)

            ids = blob[f"{name}.ids"]
            vecs = blob[f"{name}.vec"].astype(np.float32)
            payloads = {d["id"]: d["payload"] for d in index_docs(name)}
            missing = [i for i in ids.tolist() if i not in payloads]
            if missing:
                raise SystemExit(f"{name}: {len(missing)} cached ids are absent "
                                 f"from data/raw — cache and corpus disagree")

            qc.create_collection(name, vectors_config=models.VectorParams(
                size=DIM, distance=models.Distance.COSINE))
            for lo in range(0, len(ids), 512):
                sl = slice(lo, lo + 512)
                qc.upsert(name, points=models.Batch(
                    ids=ids[sl].tolist(),
                    vectors=vecs[sl].tolist(),
                    payloads=[payloads[i] for i in ids[sl].tolist()]))
            n = qc.count(name).count
            total += n
            print(f"  {name:<14} {n:>5} vectors restored")
    finally:
        qc.close()
    return total
