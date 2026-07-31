# BUILD — execute this, in this order

5 people · demo 11:40–12:00 · budget ~$15

---

## HOUR 0 — everyone together, 20 min. Do not skip.

```bash
git init && git add -A && git commit -m "scaffold"
# push somewhere all 5 can clone
./setup.sh && source .venv/bin/activate
make db                       # creates data/gap.db from schema.sql
pip install mcp
claude mcp add silent-stakeholder -- python3 $PWD/mcp_server.py
python3 -c "import tools; print(tools.polarity(['battery'],['doze','idle']))"
```

**Then agree the contract below and commit `contracts/stub_gaps.json`.**
Lanes D and E build against the stub while A and B are still running.
Nothing else parallelises until this file exists.

```json
{"gaps":[{
  "gap_id":"G1","rank":1,
  "need":"Email should keep arriving without me babysitting battery settings.",
  "verdict":"UNDER-PRIORITIZED","confidence":86,
  "components":[{"name":"Prevalence","raw":"53/1560","weight":0.30,"score":0.88}],
  "falsifier":"Wrong if any Mail-synchronization issue names Doze as root cause before 2016.",
  "roadmap_response":"#857 filed 2015-10-23 as type:enhancement, closed 2021-06-30 (5.7y)",
  "evidence":{"review_ids":["f69170c3","e81147dd","e70248d7"],"issue_numbers":[857,970,998]},
  "backtest":{"issue":857,"days":2077,"verdict":"CONFIRMED"}
}]}
```

**Two hard rules.** `review_ids` is the COMPLETE set, never a sample — the UI prints
`len()` as the headline number. Every candidate in `candidates.json` carries
`query_terms`; that field is the entire mechanism for answering "a gap you missed".

---

## LANE C — START FIRST (longest wall-clock)

`pipeline/b_label.py` — batch-label all 1,560 reviews. ~1 hr unattended.

```python
from anthropic import Anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
import tools, json

SCHEMA = {"type":"object","additionalProperties":False,
 "required":["latent_need","symptom_words","inferred_mechanism",
             "is_workaround","is_happy_friction","severity"],
 "properties":{
   "latent_need":{"type":"boolean"},
   "symptom_words":{"type":"array","items":{"type":"string"}},
   "inferred_mechanism":{"type":"string"},
   "is_workaround":{"type":"boolean"},
   "is_happy_friction":{"type":"boolean"},
   "severity":{"type":"integer"}}}

SYS = """Classify one Android email-app review (K-9 Mail, 2015-2017).
latent_need: does it imply an unmet need the user never explicitly requested?
is_workaround: does the user describe a manual step they perform to cope?
is_happy_friction: positive overall BUT reports friction?
inferred_mechanism: your best guess at the technical cause, or "unknown".
severity 1-5 from the user's lived impact, not their tone."""

reqs=[Request(custom_id=r["id"],
   params=MessageCreateParamsNonStreaming(
     model="claude-haiku-4-5", max_tokens=600,
     system=[{"type":"text","text":SYS,"cache_control":{"type":"ephemeral"}}],
     output_config={"format":{"type":"json_schema","schema":SCHEMA}},
     messages=[{"role":"user","content":r["text"][:1500]}]))
   for r in tools._reviews()]

b=Anthropic().messages.batches.create(requests=reqs)
print(b.id)   # poll, then write results into reviews.llm_* columns
```

Cost ≈ $0.64. **Kick it off, then help another lane while it runs.**

Later: `pipeline/f_critic.py` — 1 Opus 5 call per surviving gap, hostile prompt,
returns `{verdict: kill|downgrade|survive, severity, counter_issue, rebuttal_required}`.

---

## LANE A — data (unblocks everyone)

`pipeline/a_ingest.py`

```python
def load_reviews()  -> None   # data/raw/k9_reviews.json -> reviews;  ASSERT 1560
def load_issues()   -> None   # k9_issues_all.json -> issues + type_label + milestone
def load_sentences()-> None   # k9_sentences.json -> sentences;       ASSERT 4224
def derive()        -> None   # star_band, ym, days_open, is_stale_open
def build_fts()     -> None   # INSERT INTO reviews_fts(reviews_fts) VALUES('rebuild')
```

Freeze `AS_OF='2026-07-31'` into `run_manifest` — never `datetime.now()`, or your
staleness numbers drift between the slide and the stage.

`make ingest` must end with the three asserts passing. **60 min.**

---

## LANE B — clustering

`pipeline/c_cluster.py`

```python
from sentence_transformers import SentenceTransformer
import hdbscan
m = SentenceTransformer("all-mpnet-base-v2")     # local, offline, free

R = m.encode(review_texts, normalize_embeddings=True)
I = m.encode([i["title"]+" "+i["body"][:600] for i in issues], normalize_embeddings=True)
rc = hdbscan.HDBSCAN(min_cluster_size=12).fit_predict(R)
ic = hdbscan.HDBSCAN(min_cluster_size=8 ).fit_predict(I)

# THE CROSS-MATRIX — this is where gaps live
for a in review_clusters:
    for b in issue_clusters:
        cos = cosine(centroid[a], centroid[b])
        lex = jaccard(top_terms[a], top_terms[b])
        write pairs(a, b, cos, lex, divergence = cos*(1-lex))
```

| Pattern | Condition | Meaning |
|---|---|---|
| Misframe | high cos, low lex | same defect, different words |
| Orphan demand | no issue cluster cos>0.4 | IGNORED |
| Orphan supply | no review cluster | building unwanted things |

Top ~30 by `divergence` become candidates. **Discovery only — never shown as proof.**
**45 min.**

---

## LANE E — proof + scoring (HUMAN-WRITTEN, no agent)

`pipeline/d_prove.py` — mostly done, `tools.polarity()` and `tools.bridge()` work.
Per candidate: PII, bridge, gates. Gate = `PII>=1.0 AND bridge>=3 AND dated event`.

`pipeline/e_score.py`

```
Confidence = round(100*(0.55*E + 0.45*L)) - penalties     clip [5,95]

E = 0.30*Support + 0.20*Dispersion + 0.25*Friction + 0.25*Quality
    Support    = min(1, ln(1+n)/ln(101))
    Dispersion = (months_hit/18) * (1 - max_month_share)
    Friction   = MAX(star_deficit/1.0, happy_friction_share/0.40)
    Quality    = share with a PROBLEM_DISCOVERY/FEATURE_REQUEST sentence

L = 0.35*PII_norm + 0.25*Recurrence + 0.25*Mechanism + 0.15*EpicAbsence

penalties: -15 burst(>35% one month) · -12 critic material · -8 undated mechanism
```

Verdicts, first match wins:
```
gate passed + epic exists + mechanism ∉ epic terms  -> MISUNDERSTOOD
type_label=='enhancement' AND user severity high    -> UNDER-PRIORITIZED
|linked issues| == 0 and >=40 reviews               -> IGNORED
stale_frac >= 0.30                                  -> UNDER-PRIORITIZED
else                                                -> UNDER-PRIORITIZED
```
Print the counts behind every verdict. Cap at 2 MISUNDERSTOOD. **Ship 4 gaps.**
**45 min. A human writes this file — you must defend every weight on stage.**

---

## LANE D — UI

`ui/app.py` (Streamlit, build fast) then `ui/freeze.py` (static HTML, demo safe).

```python
c1,c2 = st.columns([1,2])
with c1:
    for g in gaps: st.button(f"{g['rank']}. {g['need'][:38]} · {g['verdict']} · {g['confidence']}%")
with c2:
    st.metric("Confidence", f"{g['confidence']}%")
    st.bar_chart(components)                    # defends the number
    st.caption(f"FALSIFIER: {g['falsifier']}")
    st.checkbox("4–5★ only")                    # headline toggle
    for e in evidence: st.markdown(f"`{e.id}` **{e.star}★** {e.date}"); st.info(e.text)

q = st.text_input("Ask the corpus anything")    # THE DEFENSE CONSOLE
# 4 banners: SURFACED | CONSIDERED & REJECTED | BELOW THRESHOLD | NOT IN CORPUS
```

`freeze.py` renders the final state to ONE self-contained HTML — all CSS/JS/data
inlined in `<script type="application/json">`. **`fetch()` is blocked under `file://`;
inlining is mandatory.** Render all 1,560 reviews into the page so Cmd-F works if JS dies.
**90 min + 30 min freeze.**

---

## THE KNOWLEDGE BASE YOU'RE MISSING

`contracts/external_facts.json` — hand-curated, ~15 rows. Every MISUNDERSTOOD verdict
needs a dated external event, and right now those dates are unsourced.

```json
[{"id":"android6_doze","claim":"Android 6.0 Marshmallow introduced Doze",
  "date":"2015-10-05","source":"VERIFY: developer.android.com release notes",
  "confidence":"certain","used_by":["G1"]},
 {"id":"android7_doze","claim":"Android 7.0 extended Doze to on-the-go",
  "date":"2016-08-22","source":"VERIFY","confidence":"certain","used_by":["G1"]}]
```

**Assign one person 15 minutes to verify every date and paste a real URL.** A wrong
date on your #1 gap is the single cheapest way to lose the rigor score.

---

## CHECKPOINTS

| When | Gate |
|---|---|
| +1h | `make ingest` asserts pass · batch job running · stub committed |
| +2h | `pairs` populated · UI renders stub · scoring runs on hand-made candidate |
| +3h | Real gaps end to end · critic run · backtest column filled |
| +4h | `freeze.py` → `dist/report.html` opens from `file://` |
| +5h | PDF · 2nd laptop · USB · adversarial rehearsal |

## REHEARSAL — budget it as work, not cleanup

Someone who did not build it types these into the defense console. Every one must
return a clean banner: `dark mode · calendar · swipe · ads · Exchange · spam ·
two-factor · tablet · backup · threading · unified inbox · attachments · search`.

Any blank or ugly screen is a live-demo bug.

## CUT LINE — if 90 minutes remain

1. `make db ingest` (20m)
2. Hand-write 4 gaps into `gaps.json` using `tools.polarity()` numbers (30m)
3. `freeze.py` → one HTML with inline evidence + full corpus dump (30m)
4. PDF + copy to a second laptop (10m)

**The Doze finding lives in the counts, not the model.** It survives with zero LLM calls.

**Never cut:** frozen `AS_OF` · evidence IDs · inline verbatims · the PDF · 2nd laptop.
