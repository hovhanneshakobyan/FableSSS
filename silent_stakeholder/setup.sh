#!/usr/bin/env bash
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "OK. Run: source .venv/bin/activate"
python3 -c "import anthropic,sentence_transformers,hdbscan,streamlit;print('all imports OK')"
