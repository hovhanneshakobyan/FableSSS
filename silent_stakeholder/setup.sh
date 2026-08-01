#!/usr/bin/env bash
# One-time setup for a fresh clone. The corpus (data/raw) and the built vector
# index (data/qdrant) are committed, so there is nothing to download or embed:
# this only builds the virtualenv.
#
#   ./setup.sh && make ui
#
# The smoke test below imports exactly what requirements.txt installs. It used
# to import sentence_transformers and hdbscan, neither of which was in
# requirements.txt or in any source file, so `set -e` killed setup on a clean
# machine after a successful install.
set -e
cd "$(dirname "$0")"

python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

.venv/bin/python - <<'PY'
import importlib, sys

# (module, why it must be here)
REQUIRED = [
    ("qdrant_client", "vector index"),
    ("fastembed",     "embedding model"),
    ("numpy",         "vector cache"),
    ("streamlit",     "make ui"),
    ("langgraph",     "make chat"),
]
bad = []
for mod, why in REQUIRED:
    try:
        importlib.import_module(mod)
    except Exception as exc:
        bad.append(f"  {mod:<16} ({why}) -> {type(exc).__name__}: {exc}")
if bad:
    sys.exit("FAILED — these did not install:\n" + "\n".join(bad))

# The findings render from committed JSON with no API key and no network; if
# this file is missing the clone is incomplete, which is worth saying now
# rather than on stage.
import json, os
gaps = os.path.join("data", "gaps.json")
if os.path.exists(gaps):
    n = len(json.load(open(gaps))["gaps"])
    print(f"imports OK · {n} ranked gaps present · corpus and index committed")
else:
    print("imports OK · WARNING: data/gaps.json missing — run `make gaps`")
PY

echo
echo "Done.  make ui     # findings + chat (findings need no API key)"
echo "       make gaps   # recompute the ranked gaps"
