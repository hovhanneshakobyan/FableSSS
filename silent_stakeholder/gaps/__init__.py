"""The gap engine — ranked unmet needs the roadmap is missing or under-serving.

    .venv/bin/python -m gaps run        # -> data/gaps.json + data/candidates.json
    .venv/bin/python -m gaps show
    .venv/bin/python -m gaps probe "dark mode"

Five stages, each in its own module and each auditable on its own:

    signals.py   S2  latent-need families -> lambda(r)   why it is not a counter
    themes.py    S3  candidate discovery, two routes     where hypotheses come from
    measure.py   S4  deterministic measurement           every number on a slide
    score.py     S5  confidence, verdict, rank           calibrated, decomposed
    engine.py    S7  the run + the defense console       findings AND rejects

The one rule the whole design rests on: DISCOVERY MAY PROPOSE ANYTHING,
MEASUREMENT BELIEVES NOTHING. Embeddings and keyness generate candidate
vocabulary; every term is then counted with a word-boundary regex over
data/raw/, and any term that does not survive counting is dropped. No model
and no vector score ever contributes a number to a finding.
"""
from gaps.engine import load, probe, run, write

__all__ = ["run", "load", "write", "probe"]
