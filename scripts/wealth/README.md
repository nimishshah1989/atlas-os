# wealth — Jhaveri client-portfolio ingestion + analysis

Design + findings: `docs/wealth-recommendation-framework.md`. Data (PDFs, parsed
JSON) lives OUTSIDE the repo at `/home/ubuntu/jhaveri_data/` — client PII, never
commit it.

```bash
# 1. parse (needs pdfplumber → dedicated venv, NOT the prod .venv)
/home/ubuntu/jhaveri_data/venv/bin/python scripts/wealth/parse_jhaveri.py \
    --pdf-root /home/ubuntu/jhaveri_data/pdfs --out /home/ubuntu/jhaveri_data/parsed.json

# 2-4. load / bridge to Atlas / analyze (repo venv; needs ATLAS_DB_URL from .env)
.venv/bin/python scripts/wealth/load_parsed.py --parsed /home/ubuntu/jhaveri_data/parsed.json
.venv/bin/python scripts/wealth/map_schemes.py --apply
.venv/bin/python scripts/wealth/cohort_report.py
```

Loader refuses to load any file that failed parse reconciliation (221/221 clean
as of 2026-07-18). Schema `wealth` is FM-approved, PII-hardened (no anon grants),
and outside the single-schema gate's scan surface.

## Capability demo (PROFILE/PREDICT/PRESCRIBE)

One command refreshes the whole client-intelligence engine chain — analysis
tables → per-client audit packs → plain-language narration → the standalone
capability app — end to end:

```bash
bash scripts/wealth/run_wealth_engine.sh          # full run (narrates every
                                                    # client still prose-null;
                                                    # ~30-60+ min, one `claude -p`
                                                    # call per client)
bash scripts/wealth/run_wealth_engine.sh --limit 5 # smoke run: narrate 5 clients
```

It chains, in dependency order: `build_overlap` → `build_label_check` →
`build_tax_harvest` → `build_value_statement` → `build_call_lists` →
`build_household` → `build_audit_packs` → `narrate_audit_packs.py` (any args
given to `run_wealth_engine.sh` pass straight through, e.g. `--limit`) →
`build_capability_app.py` → `validate_wealth_app.py`. `build_audit_packs` upserts, so re-running is
always safe — existing prose is preserved and only missing/changed sections
get renarrated.

Tables produced (all `wealth.*`, live Postgres): `overlap`, `label_check`,
`tax_harvest`, `value_statement`, `call_lists`, `households`, `audit_packs`
(payload + prose).

Output: `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html` — a
single self-contained HTML file (hash-routed, zero external requests) gated
by `validate_wealth_app.py` (JSON parses, no `NaN`, all client_ids resolve,
< 6 MB, zero console errors on book/calls/3 client pages). Design + build
notes: `docs/wealth-capability-atlas.md` and the implementation plan / task
briefs under `.superpowers/sdd/`.
