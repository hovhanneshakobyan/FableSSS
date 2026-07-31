"""KB layer 3 — the query API. Vectors for discovery, keywords for proof.

    from kb import KB
    kb = KB()
    kb.search("battery drains overnight", "k9_reviews", where={"star": {"lte": 2}})
    kb.polarity(["battery", "drain", "overheat"])

Two retrieval modes, deliberately separate:
  semantic  — Qdrant cosine over bge-small. Bridges vocabularies ("battery
              drain" -> "Doze"). Proposes candidates. NEVER a number on a slide.
  lexical   — word-boundary regex over data/raw/. Exact, auditable, reproducible
              by hand. This is what a count is allowed to come from.

Everything here is offline and pure. No LLM asserts anything in this file.
"""
from __future__ import annotations
import re
from functools import lru_cache

from kb import documents as docs
from kb.index import MODEL, QDRANT, client, embedder

# Reviews and issues describe the same product in different dialects. Rates are
# per 1,000 documents so the two corpora (1,560 vs 1,718) stay comparable.
PER = 1000


def _rx(terms: str | list[str]) -> re.Pattern:
    """Word-boundary OR-regex. Multi-word terms match as phrases."""
    if isinstance(terms, str):
        terms = [t.strip() for t in terms.split(",") if t.strip()]
    return re.compile("|".join(rf"\b{re.escape(t.lower())}\b" if " " not in t
                               else re.escape(t.lower()) for t in terms))


def _flt(where: dict | None):
    """{'star': {'lte': 2}, 'state': 'open', 'labels': ['a','b']} -> Filter."""
    if not where:
        return None
    from qdrant_client import models

    must = []
    for key, val in where.items():
        if isinstance(val, dict):                       # range
            if any(isinstance(v, str) for v in val.values()):
                must.append(models.FieldCondition(
                    key=key, range=models.DatetimeRange(**val)))
            else:
                must.append(models.FieldCondition(key=key, range=models.Range(**val)))
        elif isinstance(val, (list, tuple, set)):       # any-of
            must.append(models.FieldCondition(
                key=key, match=models.MatchAny(any=list(val))))
        elif val is None:
            must.append(models.IsNullCondition(is_null=models.PayloadField(key=key)))
        else:
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=val)))
    return models.Filter(must=must)


def cite(payload: dict) -> str:
    """Short, unambiguous handle for a document. Every hit must be citable."""
    if "number" in payload:
        return f"{payload.get('app', 'k9')}#{payload['number']}"
    if "sentence_id" in payload:
        return f"sent:{payload['sentence_id']}"
    return f"rev:{payload['review_id'][:8]}"


def _hit(h) -> dict:
    p = h.payload
    return {"cite": cite(p), "score": round(h.score, 4), "id": h.id,
            "text": (p.get("text") or "").strip(), "payload": p}


def _collapse(hits: list[dict], key: str, limit: int) -> list[dict]:
    """Chunk hits -> document hits. Best chunk wins, and says which it was."""
    best: dict = {}
    for h in hits:
        doc = h["payload"][key]
        if doc not in best:                     # hits arrive score-ordered
            h["chunks_matched"] = 1
            best[doc] = h
        else:
            best[doc]["chunks_matched"] += 1
    return list(best.values())[:limit]


class KB:
    """The knowledge base. Backed by data/raw/*.json and data/qdrant/."""

    def __init__(self, path: str = QDRANT, model: str = MODEL):
        self.path, self.model = path, model
        self._qc = self._emb = None

    @property
    def qc(self):
        if self._qc is None:
            self._qc = client(self.path)
        return self._qc

    @property
    def emb(self):
        if self._emb is None:               # ~2s model load, so pay it lazily
            self._emb = embedder(self.model)
        return self._emb

    def close(self) -> None:
        """Release the local-mode lock. Skipping this leaves a __del__ during
        interpreter shutdown, which prints a traceback nobody wants on stage."""
        if self._qc is not None:
            self._qc.close()
            self._qc = None

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @lru_cache(maxsize=256)
    def _vec(self, query: str) -> tuple:
        return tuple(next(iter(self.emb.embed([query]))).tolist())

    # ------------------------------------------------------------ semantic
    def search(self, query: str, collection: str = "k9_reviews",
               limit: int = 10, where: dict | None = None) -> list[dict]:
        """Nearest neighbours in one collection. Discovery, not evidence."""
        key = docs.CHUNKED.get(collection)
        # Chunked collections are over-fetched: four chunks of one long issue
        # would otherwise eat four of the caller's slots.
        hits = self.qc.query_points(collection, query=list(self._vec(query)),
                                    limit=limit * 4 if key else limit,
                                    query_filter=_flt(where)).points
        return _collapse([_hit(h) for h in hits], key, limit) if key else \
            [_hit(h) for h in hits]

    def search_all(self, query: str, limit: int = 5,
                   where: dict | None = None) -> dict[str, list[dict]]:
        """Same query against every collection — where the gap shows up."""
        return {n: self.search(query, n, limit, where) for n in docs.COLLECTIONS}

    def neighbors(self, collection: str, doc_id, limit: int = 10) -> list[dict]:
        """More-like-this from a document already in the KB (no re-embedding).

        For chunked collections this anchors on the document's first chunk —
        the title and opening paragraph, which is what the document is about.
        """
        key = docs.CHUNKED.get(collection)
        point = doc_id * 100 if key else doc_id
        hits = self.qc.query_points(collection, query=point,
                                    limit=(limit + 1) * 4 if key else limit + 1).points
        out = [_hit(h) for h in hits if h.id != point]
        if key:
            out = [h for h in _collapse(out, key, limit + 1)
                   if h["payload"][key] != doc_id]
        return out[:limit]

    def get(self, collection: str, ids: list) -> list[dict]:
        """Fetch whole documents by id — the citation lookup behind a claim.

        Served from raw JSON, not Qdrant: a citation must resolve to the full
        document (untruncated body included), and must work for ap_issues,
        which carries no vectors at all.
        """
        want = list(ids)
        by_id = {d["id"]: d for d in docs.load(collection)}
        return [{"cite": cite(by_id[i]["payload"]), "id": i,
                 "payload": by_id[i]["payload"]} for i in want if i in by_id]

    # ------------------------------------------------------------- lexical
    def lexical(self, terms: str | list[str], collection: str = "k9_reviews",
                where: dict | None = None, limit: int = 20) -> dict:
        """Exact term match over raw JSON. Auditable: anyone can grep this."""
        rx = _rx(terms)
        rows = [d for d in docs.load(collection) if _matches(d["payload"], where)]
        hit = [d for d in rows if rx.search(_haystack(d["payload"]))]
        return {"collection": collection, "terms": terms,
                "n_matched": len(hit), "n_scanned": len(rows),
                "rate_per_1k": round(PER * len(hit) / len(rows), 2) if rows else 0.0,
                "matches": [{"cite": cite(d["payload"]), "id": d["id"],
                             "text": d["text"][:200].strip()} for d in hit[:limit]]}

    def polarity(self, terms: str | list[str], issues: str = "k9_issues",
                 aligned: bool = False) -> dict:
        """The thesis metric: how much louder are users than the backlog?

        ratio > 1  users raise it more than developers file it  (unmet need)
        ratio < 1  developers track it in a vocabulary users never use

        aligned=True restricts issues to the window reviews actually cover.
        Off by default so published numbers don't move under anyone, but on is
        the defensible comparison: it moved `battery` from 1.79x to 1.46x.
        """
        lo, hi = docs.review_window()
        where = {"created_at": {"gte": lo, "lte": hi}} if aligned else None
        rev = self.lexical(terms, "k9_reviews", limit=0)
        iss = self.lexical(terms, issues, where=where, limit=0)
        ratio = (rev["rate_per_1k"] / iss["rate_per_1k"]) if iss["rate_per_1k"] else None
        return {"terms": terms,
                "reviews": {"n": rev["n_matched"], "of": rev["n_scanned"],
                            "per_1k": rev["rate_per_1k"]},
                "issues": {"n": iss["n_matched"], "of": iss["n_scanned"],
                           "per_1k": iss["rate_per_1k"]},
                "ratio_user_over_dev": round(ratio, 2) if ratio else None,
                "reading": "user-led" if ratio and ratio > 1.2 else
                           "dev-led" if ratio and ratio < 0.83 else "balanced",
                "window": f"{lo}..{hi}" if aligned else "full corpora (unaligned)"}

    def control(self, terms: str | list[str]) -> dict:
        """K-9's backlog vs AntennaPod's, same terms. The negative control.

        A term that is just as loud in an unrelated Android app's issues is a
        platform artefact, not a K-9 gap. Keyword only — ap_issues carries no
        vectors, because a control is a rate comparison, not a neighbour search.
        """
        k9 = self.lexical(terms, "k9_issues", limit=0)
        ap = self.lexical(terms, "ap_issues", limit=0)
        ratio = (k9["rate_per_1k"] / ap["rate_per_1k"]) if ap["rate_per_1k"] else None
        return {"terms": terms,
                "k9_issues": {"n": k9["n_matched"], "of": k9["n_scanned"],
                              "per_1k": k9["rate_per_1k"]},
                "ap_issues": {"n": ap["n_matched"], "of": ap["n_scanned"],
                              "per_1k": ap["rate_per_1k"]},
                "ratio_k9_over_control": round(ratio, 2) if ratio else None,
                "reading": "k9-specific" if ratio and ratio > 1.5 else
                           "platform-wide" if ratio is not None and ratio < 1.5
                           else "absent in control"}

    # --------------------------------------------------------------- meta
    def stats(self) -> dict:
        out = {}
        for name in docs.SOURCES:
            n = len(docs.load(name))
            if name not in docs.COLLECTIONS:      # raw-only corpus (the control)
                out[name] = {"documents": n, "vectors": None, "in_sync": True}
                continue
            want = len(docs.index_docs(name))     # chunks, where they differ
            got = self.qc.count(name).count if self.qc.collection_exists(name) else 0
            out[name] = {"documents": n, "vectors": got, "in_sync": got == want,
                         "expected": want}
        return out


def _haystack(p: dict) -> str:
    """Everything a keyword may legitimately match on, lowercased."""
    return " ".join(str(p.get(k) or "") for k in ("title", "body", "text")).lower()


def _matches(p: dict, where: dict | None) -> bool:
    """The `where` semantics of search(), replayed in Python for raw scans."""
    if not where:
        return True
    for key, val in where.items():
        got = p.get(key)
        if isinstance(val, dict):
            if got is None:
                return False
            if "gte" in val and got < val["gte"]:
                return False
            if "lte" in val and got > val["lte"]:
                return False
            if "gt" in val and got <= val["gt"]:
                return False
            if "lt" in val and got >= val["lt"]:
                return False
        elif isinstance(val, (list, tuple, set)):
            if isinstance(got, list):
                if not set(got) & set(val):
                    return False
            elif got not in val:
                return False
        elif isinstance(got, list):
            if val not in got:
                return False
        elif got != val:
            return False
    return True
