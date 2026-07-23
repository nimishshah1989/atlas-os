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
