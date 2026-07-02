# atlas-os

Atlas is a discovery-first **equity-intelligence board** for Indian markets. It ingests
real market data nightly, scores stocks / ETFs / funds / sectors through a transparent
lens methodology, and serves the result as a glass-box web board.

It is self-contained: one Postgres schema, its own ingestion, its own compute, its own
frontend. Nothing routes through an external service except the raw data feeds.

## Architecture

```
feeds ─▶ scripts/foundation/  ─▶  atlas_foundation  ─▶  frontend/ (Next.js board)
(Kite, NSE, AMFI,   ingest + compute       (single Supabase        reads Postgres
 Morningstar,       (atlas/ modulith)       Postgres schema)        directly
 screener.in)
```

- **`atlas_foundation`** is the only data schema. Every read/write goes here.
- **`atlas/`** — the compute modulith (`compute`, `intraday`, `lenses`) + `config`/`db`.
- **`scripts/foundation/`** — ingestion + derived-table builders (all real sources).
- **`scripts/ops/atlas_daily.sh`** — the nightly orchestrator (16:00 IST): ingest →
  compute → gates → health snapshot.
- **`frontend/`** — Next.js board reading `atlas_foundation` via Supabase. No API backend.
- **`migrations/`** — a single squashed baseline that reproduces the live schema.

## Running it

```bash
# Python env
python -m venv .venv && source .venv/bin/activate
uv sync --extra dev                    # or: pip install -e '.[dev]'
cp .env.example .env                    # set ATLAS_DB_URL (Supabase connection string)

# Verify DB connectivity
PYTHONPATH=.:scripts/foundation .venv/bin/python -c "import _db; print(_db.eod_cutoff())"

# Run the nightly pipeline once (ingest → compute → gates)
bash scripts/ops/atlas_daily.sh

# Unit tests (fast, real records — no synthetic data; see RULE #0 in CLAUDE.md)
pytest tests/unit -m unit -q

# Frontend
cd frontend && npm install && npm run dev      # dev board on :3000
```

## Gates

- `scripts/ops/schema_gate.py` — proves every live read is in `atlas_foundation` (must be 0).
- `scripts/foundation/validate_lenses.py --check A|B` — asserts on REAL produced scores.
- `scripts/ops/freshness_guard.py` — fails loud if any served table is stale.
- CI (`.github/workflows/ci.yml`): ruff + pyright ratchet + unit tests + a fresh-DB
  `alembic upgrade head` against the baseline.

## Docs

`CLAUDE.md` (engineering rules) · `CONTEXT.md` (glossary) · `docs/refresh-schedule.md` +
`docs/table-census.md` (data model) · `docs/deploy.md` + `docs/deploy-hygiene.md` ·
`docs/engineering-process.md` (CI gates) · `docs/adr/` (decisions).
