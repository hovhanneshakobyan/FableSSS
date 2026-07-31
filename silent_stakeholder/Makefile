.PHONY: db ingest control cluster score ui freeze all verify chat chat-dry gaps
db:      ; sqlite3 data/gap.db < schema.sql
ingest:  ; python3 pipeline/a_ingest.py
control: ; python3 pipeline/a_ingest.py --app antennapod
verify:  ; python3 pipeline/verify.py
embed:   ; .venv/bin/python pipeline/c_embed.py
probe:   ; .venv/bin/python pipeline/c_embed.py --probe "$(Q)"
label:   ; python3 pipeline/b_label.py
cluster: ; python3 pipeline/c_cluster.py
prove:   ; python3 pipeline/d_prove.py
score:   ; python3 pipeline/e_score.py
gaps:    ; .venv/bin/python -m gaps run
gapshow: ; .venv/bin/python -m gaps show
chat:    ; .venv/bin/python -m agent
chat-dry:; .venv/bin/python -m agent --dry
ui:      ; .venv/bin/streamlit run ui/app.py
freeze:  ; python3 ui/freeze.py
all: db ingest cluster prove score
