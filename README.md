# atlas-os

Atlas — Adaptive Technical Lens for Asset States. Indian wealth-management
decision engine. Reads OHLCV / NAV / holdings from JIP Data Core (Layer 1,
read-only), computes the four primitives + states + decisions per the
methodology lock (Layer 3), serves results via a thin FastAPI + Streamlit
stack.

This repo follows the layout defined in `docs/01_BACKEND_ARCHITECTURE.md`
Section 11.

## Sources of truth

| Document | Owns |
|---|---|
| `docs/00_METHODOLOGY_LOCK.md` | What the system computes (formulas, states, decisions) |
| `docs/01_BACKEND_ARCHITECTURE.md` | How the system is built (conventions, libraries, topology) |
| `docs/02_DATABASE_SCHEMA.md` | Every column of every table |
| `docs/03_VALIDATION_FRAMEWORK.md` | What "done" means for every milestone |
| `docs/04_THRESHOLD_CATALOG.md` | The 35 tunable thresholds + tuning discipline |
| `docs/milestones/ATLAS_M*.md` | Build-time instructions for milestone N |
| `prds/00_INFRA_DECISIONS.md` | Decisions taken at build start (Supabase pivot, F1-F7 fixes, etc.) |

When milestone docs and the methodology lock disagree, **methodology wins**.
The seven drifts found in the M5 milestone draft (F1-F7) have been patched
to match methodology — see `prds/00_INFRA_DECISIONS.md` Section 5.

## Build sequencing

| Milestone | Status | Description |
|---|---|---|
| M0 — Data Core Prep | ✅ Complete | Gap fill, ETF holdings ingest, JIP cleanup |
| M1 — Schema + Reference | ⏳ In progress | This repo's current focus. Awaits Supabase migration of JIP tables. |
| M2 — Stock + ETF Metrics | Pending M1 signoff | The four primitives + state classification |
| M3 — Sector + Market Regime | Pending M2 | Aggregation + regime classifier |
| M4 — MF Three-Lens | Pending M3 | Fund decision support |
| M5 — Decision Engine | Pending M4 | Investability + entry/exit triggers |

## Running M1

### One-time setup

```bash
# 1. Install deps + this package in editable mode
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# 2. Configure DB connection
cp .env.example .env
# Edit .env — set ATLAS_DB_URL to your Supabase connection string

# 3. Verify connectivity
python -m atlas.db
# Expected output: PostgreSQL version, current_database, current_user
```

### Apply migrations + lock universe

```bash
python scripts/m1_run.py
```

This is idempotent — re-running upserts existing rows. Output is the M1
readiness summary with row counts per universe table.

### Run unit tests

```bash
pytest tests/unit/
```

Unit tests cover the pure-Python helpers (tier classification, ETF theme
classification, fund category mapping, threshold catalog integrity). They
run without a database.

### Validation report

After `m1_run.py` succeeds:

```bash
python -m atlas.validation.tier1_raw   # not yet implemented (M1 Phase D)
```

## Layout

```
atlas-os/
├── docs/                     foundation + milestone docs (source of truth)
├── prds/                     decisions and inventories from M0
├── output/                   M0 artefacts (GAP_MAP, validation, inventory)
├── migrations/               Alembic migrations 001-010 → atlas schema + roles
├── atlas/                    main package
│   ├── config.py             ATLAS_DB_URL + lock date
│   ├── db.py                 SQLAlchemy engine + load_thresholds helper
│   └── universe/             M1 universe lock (sectors, stocks, ETFs, …)
├── scripts/
│   └── m1_run.py             M1 entry point — migrations + universe lock
├── tests/unit/               pure-Python tests (no DB)
├── src/atlas_os/             legacy M0-inventory module — kept for reference
├── pyproject.toml
├── alembic.ini
└── .env.example
```

## Hooks and engineering rules

This project obeys the global rules in `~/.claude/CLAUDE.md`:

- No `float` for money — `NUMERIC(18,4)` or `NUMERIC(20,4)` everywhere.
- No bare `except:` clauses.
- Library discipline (architecture 5.5): EMAs from pandas-ta, drawdowns from
  empyrical, no hand-rolled formulas at the primitive layer.
- Threshold discipline (architecture 5.6): every classification rule receives
  thresholds as a dict argument; never hardcoded.
- Tier 1-5 validation per milestone DoD.

Pre-commit hooks (see `.pre-commit-config.yaml`) enforce these at edit time.
