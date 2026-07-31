"""Knowledge base for The Silent Stakeholder.

Two inputs, nothing else:
  data/raw/*.json   the corpora (reviews, sentences, K-9 issues, AntennaPod control)
  data/qdrant/      local-mode vector store — the three K-9 corpora only

The AntennaPod control is loaded from raw and counted, never embedded.

    from kb import KB
    KB().search("battery drains overnight", "k9_issues")
"""
from kb.documents import AS_OF, COLLECTIONS, SOURCES, load
from kb.index import MODEL, QDRANT, build_all
from kb.search import KB, cite

__all__ = ["KB", "AS_OF", "COLLECTIONS", "SOURCES", "MODEL", "QDRANT",
           "build_all", "cite", "load"]
