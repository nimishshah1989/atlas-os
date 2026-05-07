# Atlas-M1 — Schema and Reference Data

**Document:** ATLAS_M1_SCHEMA_AND_REFERENCE
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Builder:** Claude Code (intended executor)
**References:**
- `00_METHODOLOGY_LOCK.md` (what we're building toward)
- `01_BACKEND_ARCHITECTURE.md` (conventions, naming, topology)
- `02_DATABASE_SCHEMA.md` (every table this milestone creates)
- `03_VALIDATION_FRAMEWORK.md` (what "done" means)

---

## 1. Goal

Create the Atlas database schema and populate all reference tables (Layer 2). After this milestone:

- The `atlas` schema exists in the `data_engine` database with all 28 tables created
- All reference tables are populated with locked v0 data
- The 750-stock, 100-ETF, 75-index, ~400-fund universe is locked and queryable
- The NSE sector taxonomy is materialized from `de_instrument.sector`
- Database roles (`atlas_writer`, `atlas_reader`, `atlas_admin`) are created with correct permissions

**No metrics are computed in this milestone.** No state classification, no decisions. Just the foundation.

This milestone is intentionally bounded so it can be completed and verified before any compute work begins. Atlas-M2 (the metric engine) cannot start until Atlas-M1 is verified complete.

---

## 2. Dependencies

### 2.1 Predecessors

None. This is the first Atlas milestone.

### 2.2 Required External Resources

| Resource | Purpose | Status |
|---|---|---|
| JIP Data Core RDS | Source for reference data | Live: `jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com` |
| AWS account `jhaveritech` | Database access | Active |
| Atlas repo | Where code lives | To be created at start of M1 |

### 2.3 Required JIP Data Core Tables (Read-Only)

| Table | Used For |
|---|---|
| `de_instrument` | Stock master with sector/industry; populates `atlas_universe_stocks` |
| `de_etf_master` | ETF master; populates `atlas_universe_etfs` |
| `de_index_master` | Index master; populates `atlas_universe_indices` |
| `de_mf_master` | Fund master; populates `atlas_universe_funds` |
| `de_sector_mapping` | Sector-to-NSE-index mapping; populates `atlas_sector_master` |
| `de_etf_ohlcv` | For ETF universe ranking by 60-day median traded value |
| `de_index_constituents` | For tier classification (Nifty 100/Midcap 150/etc. memberships) |
| `de_mf_nav_daily` | For verifying fund universe filter (NAV data exists) |

---

## 3. Deliverables

### 3.1 Code Deliverables

```
atlas-backend/
├── README.md
├── pyproject.toml                              # Dependencies pinned per architecture Section 5.1
├── .env.example                                # ATLAS_DB_URL placeholder
├── docs/
│   ├── 00_METHODOLOGY_LOCK.md                  # Copied from this spec
│   ├── 01_BACKEND_ARCHITECTURE.md              # Copied from this spec
│   ├── 02_DATABASE_SCHEMA.md                   # Copied from this spec
│   ├── 03_VALIDATION_FRAMEWORK.md              # Copied from this spec
│   └── milestones/
│       └── ATLAS_M1_SCHEMA_AND_REFERENCE.md    # This document
├── migrations/
│   ├── 001_create_atlas_schema.sql
│   ├── 002_create_universe_tables.sql
│   ├── 003_create_master_tables.sql
│   ├── 008_create_indexes.sql                  # Just for the tables created in M1
│   ├── 009_create_constraints.sql              # Just for the tables created in M1
│   └── 010_grant_role_permissions.sql
├── atlas/
│   ├── __init__.py
│   ├── config.py                               # Connection settings, env loading
│   ├── db.py                                   # SQLAlchemy engine
│   └── universe/
│       ├── __init__.py
│       ├── lock.py                             # Universe locking logic
│       ├── stocks.py                           # Stock universe builder
│       ├── etfs.py                             # ETF universe builder
│       ├── indices.py                          # Index universe builder
│       ├── funds.py                            # Fund universe builder
│       └── sectors.py                          # Sector taxonomy builder
├── scripts/
│   └── m1_run.py                               # Entry point for Atlas-M1 execution
├── tests/
│   └── unit/
│       └── test_universe_filters.py
└── docs/validation/
    └── validation_M1_<date>.md                 # The DoD artifact
```

### 3.2 Database Deliverables

After M1 execution, the following must exist in the `atlas` schema:

**Tables created (all with indexes and constraints per `02_DATABASE_SCHEMA.md`):**
- `atlas_universe_stocks`
- `atlas_universe_etfs`
- `atlas_universe_indices`
- `atlas_universe_funds`
- `atlas_sector_master`
- `atlas_benchmark_master`
- `atlas_fund_category_benchmark_map`

Plus all metric/state/decision/operational tables (created with no rows, ready for Atlas-M2):
- `atlas_stock_metrics_daily` (empty)
- `atlas_stock_states_daily` (empty)
- `atlas_stock_decisions_daily` (empty)
- `atlas_etf_metrics_daily` (empty)
- `atlas_etf_states_daily` (empty)
- `atlas_etf_decisions_daily` (empty)
- `atlas_index_metrics_daily` (empty)
- `atlas_sector_metrics_daily` (empty)
- `atlas_sector_states_daily` (empty)
- `atlas_market_regime_daily` (empty)
- `atlas_fund_metrics_daily` (empty)
- `atlas_fund_lens_monthly` (empty)
- `atlas_fund_states_daily` (empty)
- `atlas_fund_decisions_daily` (empty)
- `atlas_run_log` (empty)
- `atlas_validation_results` (empty)
- `atlas_benchmark_returns_cache` (empty)
- 4 quarantine tables (empty)

**Reference tables populated:**

| Table | Expected Row Count |
|---|---|
| `atlas_universe_stocks` | 750 |
| `atlas_universe_etfs` | 100 |
| `atlas_universe_indices` | 75 |
| `atlas_universe_funds` | 350–450 |
| `atlas_sector_master` | ~20 (whatever NSE classification gives us) |
| `atlas_benchmark_master` | 9 |
| `atlas_fund_category_benchmark_map` | 8–10 |
| `atlas_thresholds` | 35 |
| `atlas_threshold_history` | 35 (initial seed entries) |

**Database roles created with correct permissions:**
- `atlas_writer`: INSERT/UPDATE/DELETE on `atlas.*`; SELECT on `public.de_*`
- `atlas_reader`: SELECT on `atlas.*` only
- `atlas_admin`: DDL on `atlas.*`; SELECT on `public.de_*`

### 3.3 Documentation Deliverables

- `docs/validation/validation_M1_<date>.md` — the DoD validation report
- `README.md` with: setup instructions, how to run M1, repo structure overview
- Inline docstrings on every function in `atlas/universe/`

---

## 4. Phase A — Repository Setup

### 4.1 Goal

Initialize the Atlas backend repository with the documented structure, install dependencies, verify connectivity to JIP Data Core.

### 4.2 Steps

**Step 1 — Initialize repository structure**

Create directory structure per `01_BACKEND_ARCHITECTURE.md` Section 11. Ensure all directories from the tree exist.

**Step 2 — Create `pyproject.toml`**

Pin all dependencies per `01_BACKEND_ARCHITECTURE.md` Section 5.1:

```toml
[project]
name = "atlas-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "polars>=0.20",
    "pandas>=2.1",
    "pandas-ta==0.3.14b0",
    "empyrical==0.5.5",
    "scipy>=1.11",
    "numpy>=1.26",
    "sqlalchemy>=2.0",
    "psycopg2-binary>=2.9",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1",
]
```

**Step 3 — Create `.env.example`**

```
ATLAS_DB_URL=postgresql://atlas_writer:PASSWORD@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine
```

**Step 4 — Create `atlas/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_URL = os.environ["ATLAS_DB_URL"]
    SCHEMA_NAME = "atlas"
    SOURCE_SCHEMA = "public"  # JIP Data Core
    UNIVERSE_LOCK_DATE = "2026-05-04"  # Update to actual M1 execution date
    HISTORICAL_START_DATE = "2014-04-01"
```

**Step 5 — Create `atlas/db.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from atlas.config import Config

def get_engine() -> Engine:
    return create_engine(Config.DB_URL, pool_pre_ping=True)
```

**Step 6 — Verify connectivity**

Run a simple connectivity check:

```python
from atlas.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    result = conn.execute("SELECT current_database(), current_user")
    print(result.fetchone())
    # Expected output: ('data_engine', 'atlas_admin') or similar
```

### 4.3 Phase A Definition of Done

- [ ] Directory structure matches `01_BACKEND_ARCHITECTURE.md` Section 11
- [ ] `pyproject.toml` lists all dependencies with version pins
- [ ] `.env.example` documents `ATLAS_DB_URL`
- [ ] `atlas/config.py` and `atlas/db.py` exist and import without errors
- [ ] Connectivity verification succeeds against `data_engine` database

---

## 5. Phase B — Schema Creation

### 5.1 Goal

Create the `atlas` schema, all 28 tables, all indexes, all constraints, and all database roles.

### 5.2 Steps

**Step 1 — Create migration `001_create_atlas_schema.sql`**

```sql
-- Migration 001: Create atlas schema
CREATE SCHEMA IF NOT EXISTS atlas;
COMMENT ON SCHEMA atlas IS 'Atlas — Adaptive Technical Lens for Asset States';
```

**Step 2 — Create migration `002_create_universe_tables.sql`**

Translate `02_DATABASE_SCHEMA.md` Section 2.1, 2.2, 2.3, 2.4 into CREATE TABLE statements. Use `CREATE TABLE IF NOT EXISTS` for idempotence. Include all column definitions exactly as specified in the schema document.

**Step 3 — Create migration `003_create_master_tables.sql`**

Translate `02_DATABASE_SCHEMA.md` Section 2.5, 2.6, 2.7 into CREATE TABLE statements.

**Step 4 — Create migration `004_create_metric_tables.sql`**

Translate `02_DATABASE_SCHEMA.md` Section 3 (all 7 metric tables).

**Step 5 — Create migration `005_create_state_tables.sql`**

Translate `02_DATABASE_SCHEMA.md` Section 4 (all 4 state tables).

**Step 6 — Create migration `006_create_decision_tables.sql`**

Translate `02_DATABASE_SCHEMA.md` Section 5 (all 3 decision tables).

**Step 7 — Create migration `007_create_operational_tables.sql`**

Translate `02_DATABASE_SCHEMA.md` Section 6 (run log, validation results, benchmark cache, 4 quarantine tables).

**Step 8 — Create migration `008_create_indexes.sql`**

All indexes from `02_DATABASE_SCHEMA.md` Sections 2–6. Use `CREATE INDEX IF NOT EXISTS`.

**Step 9 — Create migration `009_create_constraints.sql`**

All CHECK constraints from `02_DATABASE_SCHEMA.md` Section 8.2. Foreign keys per Section 8.1.

**Step 10 — Create migration `010_grant_role_permissions.sql`**

```sql
-- Migration 010: Create roles and grant permissions

-- Atlas writer (compute pipelines)
DO $$ BEGIN
    CREATE ROLE atlas_writer LOGIN PASSWORD 'CHANGE_ME_BEFORE_DEPLOY';
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Role atlas_writer already exists, skipping creation';
END $$;

GRANT USAGE ON SCHEMA atlas TO atlas_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA atlas TO atlas_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA atlas TO atlas_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA atlas 
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO atlas_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA atlas 
    GRANT USAGE ON SEQUENCES TO atlas_writer;
GRANT USAGE ON SCHEMA public TO atlas_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_writer;

-- Atlas reader (UI, FastAPI)
DO $$ BEGIN
    CREATE ROLE atlas_reader LOGIN PASSWORD 'CHANGE_ME_BEFORE_DEPLOY';
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Role atlas_reader already exists, skipping creation';
END $$;

GRANT USAGE ON SCHEMA atlas TO atlas_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA atlas TO atlas_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA atlas 
    GRANT SELECT ON TABLES TO atlas_reader;

-- Atlas admin (migrations)
DO $$ BEGIN
    CREATE ROLE atlas_admin LOGIN PASSWORD 'CHANGE_ME_BEFORE_DEPLOY';
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Role atlas_admin already exists, skipping creation';
END $$;

GRANT ALL ON SCHEMA atlas TO atlas_admin;
GRANT ALL ON ALL TABLES IN SCHEMA atlas TO atlas_admin;
GRANT USAGE ON SCHEMA public TO atlas_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_admin;
```

**IMPORTANT:** The actual passwords must be set securely (AWS Secrets Manager, environment variables, etc.) — the `CHANGE_ME_BEFORE_DEPLOY` placeholder must be replaced before any deployment. Document the password management approach in `README.md`.

**Step 11 — Run migrations in order**

Execute migrations 001 through 010 against the `data_engine` database, connected as `atlas_admin` (or a privileged user that can create schemas and roles).

### 5.3 Phase B Definition of Done

- [ ] `atlas` schema exists in `data_engine` database
- [ ] All 28 tables exist in `atlas` schema (verified via `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'atlas'`)
- [ ] All indexes exist (verified via `SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'atlas'`)
- [ ] All check constraints exist
- [ ] Three roles exist: `atlas_writer`, `atlas_reader`, `atlas_admin`
- [ ] `atlas_writer` can SELECT from `public.de_*` tables (test query)
- [ ] `atlas_reader` cannot INSERT into `atlas.*` tables (test query, expect permission denied)

---

## 6. Phase C — Reference Data Population

### 6.1 Goal

Populate the seven reference tables with locked v0 data drawn from JIP Data Core.

### 6.2 Steps

**Step 1 — Implement `atlas/universe/sectors.py`**

Materialize the NSE sector taxonomy by querying `de_instrument`:

```python
import polars as pl
from sqlalchemy import text
from atlas.db import get_engine

def build_sector_master() -> pl.DataFrame:
    """
    Lock the NSE sector taxonomy by querying de_instrument.sector.
    Joins with de_sector_mapping to get NSE sectoral index linkage.
    """
    engine = get_engine()
    
    # Get distinct sectors from de_instrument
    query_sectors = """
    SELECT DISTINCT sector 
    FROM public.de_instrument 
    WHERE is_active = true 
      AND sector IS NOT NULL
    ORDER BY sector
    """
    
    # Get sector-to-index mapping
    query_mapping = """
    SELECT 
        jip_sector_name, 
        primary_nse_index, 
        secondary_nse_indices, 
        notes
    FROM public.de_sector_mapping
    """
    
    with engine.connect() as conn:
        sectors_df = pl.read_database(query_sectors, conn)
        mapping_df = pl.read_database(query_mapping, conn)
    
    # Left-join: every sector gets a row, with NULL primary_nse_index if no mapping exists
    result = sectors_df.join(
        mapping_df,
        left_on="sector",
        right_on="jip_sector_name",
        how="left"
    ).select([
        pl.col("sector").alias("sector_name"),
        pl.col("primary_nse_index"),
        pl.col("secondary_nse_indices"),
        pl.lit("NIFTY 500").alias("fallback_benchmark"),
        pl.col("notes"),
        pl.lit(True).alias("is_active"),
    ])
    
    return result

def populate_atlas_sector_master():
    df = build_sector_master()
    engine = get_engine()
    df.write_database("atlas.atlas_sector_master", engine, if_table_exists="append")
    print(f"Populated atlas_sector_master with {len(df)} rows")
```

**Step 2 — Implement `atlas/universe/stocks.py`**

Lock the 750-stock universe with tier classification:

```python
import polars as pl
from sqlalchemy import text
from atlas.db import get_engine
from atlas.config import Config

def build_stock_universe() -> pl.DataFrame:
    """
    Build the 750-stock universe:
    - 500 stocks from Nifty 500 (where in_nifty_500 = TRUE in de_instrument)
    - +250 next stocks by 60-day median traded value (from de_equity_ohlcv)
    - Tag each with tier (Large/Mid/Small/Micro) using nifty_50, nifty_100 flags + index_constituents
    """
    engine = get_engine()
    
    # Query 1: Nifty 500 stocks
    query_n500 = """
    SELECT 
        id AS instrument_id,
        symbol,
        company_name,
        sector,
        industry,
        nifty_50 AS in_nifty_50,
        (nifty_100 OR nifty_50) AS in_nifty_100,
        nifty_500 AS in_nifty_500,
        listing_date
    FROM public.de_instrument
    WHERE is_active = TRUE 
      AND nifty_500 = TRUE
    """
    
    # Query 2: Microcap candidates — top by 60-day median traded value, excluding Nifty 500
    query_microcap = f"""
    WITH recent_volume AS (
        SELECT 
            o.instrument_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.close * o.volume) AS median_traded_value_60d
        FROM public.de_equity_ohlcv o
        WHERE o.date >= (CURRENT_DATE - INTERVAL '90 days')
        GROUP BY o.instrument_id
        HAVING COUNT(*) >= 30  -- At least 30 trading days in window
    )
    SELECT 
        i.id AS instrument_id,
        i.symbol,
        i.company_name,
        i.sector,
        i.industry,
        i.nifty_50 AS in_nifty_50,
        (i.nifty_100 OR i.nifty_50) AS in_nifty_100,
        i.nifty_500 AS in_nifty_500,
        i.listing_date,
        rv.median_traded_value_60d
    FROM public.de_instrument i
    JOIN recent_volume rv ON rv.instrument_id = i.id
    WHERE i.is_active = TRUE 
      AND i.nifty_500 = FALSE
    ORDER BY rv.median_traded_value_60d DESC
    LIMIT 250
    """
    
    with engine.connect() as conn:
        n500_df = pl.read_database(query_n500, conn)
        microcap_df = pl.read_database(query_microcap, conn)
    
    # Combine
    universe_df = pl.concat([
        n500_df.with_columns(pl.lit(None).cast(pl.Float64).alias("median_traded_value_60d")),
        microcap_df,
    ])
    
    # Tier classification
    universe_df = universe_df.with_columns(
        pl.when(pl.col("in_nifty_100"))
            .then(pl.lit("Large"))
        .when(pl.col("in_nifty_500") & ~pl.col("in_nifty_100"))
            .then(
                # Distinguish Mid (Nifty Midcap 150) from Small (Nifty Smallcap 250)
                # Based on whether they're in the next 150 by mcap among non-Nifty100 names
                # For v0 simplicity: use index_constituents to verify Nifty Midcap 150 membership
                # Otherwise classify as Small
                pl.lit("Small")  # Will be refined below via index_constituents join
            )
        .otherwise(pl.lit("Micro"))
        .alias("tier")
    )
    
    # Refine Mid/Small using de_index_constituents
    midcap_constituents = pl.read_database("""
        SELECT DISTINCT instrument_id 
        FROM public.de_index_constituents 
        WHERE index_name = 'NIFTY MIDCAP 150'
    """, engine)
    midcap_ids = set(midcap_constituents["instrument_id"].to_list())
    
    universe_df = universe_df.with_columns(
        pl.when(
            (pl.col("tier") == "Small") & 
            pl.col("instrument_id").is_in(list(midcap_ids))
        ).then(pl.lit("Mid"))
        .otherwise(pl.col("tier"))
        .alias("tier")
    )
    
    # Add audit columns
    universe_df = universe_df.with_columns([
        pl.lit(Config.UNIVERSE_LOCK_DATE).str.to_date().alias("effective_from"),
        pl.lit(None).cast(pl.Date).alias("effective_to"),
    ])
    
    # Final selection
    return universe_df.select([
        "instrument_id", "symbol", "company_name", "tier", "sector", "industry",
        "in_nifty_50", "in_nifty_100", "in_nifty_500", "listing_date",
        "effective_from", "effective_to",
    ])

def populate_atlas_universe_stocks():
    df = build_stock_universe()
    assert len(df) == 750, f"Expected 750 stocks, got {len(df)}"
    
    engine = get_engine()
    df.write_database("atlas.atlas_universe_stocks", engine, if_table_exists="append")
    print(f"Populated atlas_universe_stocks with {len(df)} rows")
    
    # Tier distribution check
    tier_counts = df.group_by("tier").len().sort("tier")
    print("Tier distribution:")
    print(tier_counts)
```

**Step 3 — Implement `atlas/universe/etfs.py`**

```python
def build_etf_universe() -> pl.DataFrame:
    """
    Top 100 ETFs by 60-day median traded value.
    Theme classification (Broad/Sectoral/Thematic) based on ETF master metadata.
    """
    engine = get_engine()
    
    query = """
    WITH recent_volume AS (
        SELECT 
            o.ticker,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.close * o.volume) AS median_traded_value_60d
        FROM public.de_etf_ohlcv o
        WHERE o.date >= (CURRENT_DATE - INTERVAL '90 days')
        GROUP BY o.ticker
        HAVING COUNT(*) >= 30
    )
    SELECT 
        m.ticker,
        m.isin,
        m.fund_house,
        m.etf_name,
        m.asset_class,
        m.inception_date,
        m.category,  -- For theme inference
        rv.median_traded_value_60d
    FROM public.de_etf_master m
    JOIN recent_volume rv ON rv.ticker = m.ticker
    ORDER BY rv.median_traded_value_60d DESC
    LIMIT 100
    """
    
    with engine.connect() as conn:
        etf_df = pl.read_database(query, conn)
    
    # Theme classification logic
    # Broad: tracks Nifty 50, Nifty 100, Nifty 500, Nifty Next 50, Sensex
    # Sectoral: tracks single NSE sector index (Nifty Bank, Nifty IT, etc.)
    # Thematic: everything else (factor, smart-beta, thematic, international, gold)
    
    broad_keywords = ["NIFTY 50", "NIFTY100", "NIFTY 500", "NIFTYNEXT50", "SENSEX", "BSE 100"]
    sectoral_keywords = ["BANK", "IT", "FMCG", "AUTO", "PHARMA", "METAL", "ENERGY", 
                          "REALTY", "MEDIA", "PSUBANK", "HEALTHCARE"]
    
    def classify_theme(etf_name: str, category: str | None) -> tuple[str, str | None]:
        name_upper = (etf_name or "").upper()
        cat_upper = (category or "").upper()
        
        # Check broad first
        for kw in broad_keywords:
            if kw in name_upper:
                return ("Broad", None)
        
        # Check sectoral
        for kw in sectoral_keywords:
            if kw in name_upper:
                return ("Sectoral", kw.title())  # linked_sector
        
        # Default: Thematic
        return ("Thematic", None)
    
    themes = []
    linked_sectors = []
    for row in etf_df.iter_rows(named=True):
        theme, linked = classify_theme(row["etf_name"], row.get("category"))
        themes.append(theme)
        linked_sectors.append(linked)
    
    etf_df = etf_df.with_columns([
        pl.Series("theme", themes),
        pl.Series("linked_sector", linked_sectors),
        pl.lit(None).cast(pl.Utf8).alias("linked_index"),  # Optional; can be backfilled later
        pl.lit(Config.UNIVERSE_LOCK_DATE).str.to_date().alias("effective_from"),
        pl.lit(None).cast(pl.Date).alias("effective_to"),
    ])
    
    return etf_df.select([
        "ticker", "isin", "fund_house", "etf_name", "theme", 
        "linked_sector", "linked_index", "asset_class", "inception_date",
        "effective_from", "effective_to"
    ])

def populate_atlas_universe_etfs():
    df = build_etf_universe()
    assert len(df) == 100, f"Expected 100 ETFs, got {len(df)}"
    
    engine = get_engine()
    df.write_database("atlas.atlas_universe_etfs", engine, if_table_exists="append")
    print(f"Populated atlas_universe_etfs with {len(df)} rows")
```

**Step 4 — Implement `atlas/universe/indices.py`**

```python
def build_index_universe() -> pl.DataFrame:
    """
    Curated 75-index universe drawn from de_index_master.
    Role classification per methodology Section 6 + Architecture conventions.
    """
    # Define the 75-index curated list explicitly
    # This list is locked here; future changes require methodology revision
    
    BROAD = [
        "NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY 500", 
        "NIFTY MIDCAP 50", "NIFTY MIDCAP 100", "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 50", "NIFTY SMALLCAP 100", "NIFTY SMALLCAP 250",
        "NIFTY MICROCAP 250", "NIFTY TOTAL MARKET", "NIFTY LARGEMIDCAP 250",
    ]
    
    SECTORAL = [
        "NIFTY BANK", "NIFTY IT", "NIFTY FMCG", "NIFTY AUTO", 
        "NIFTY PHARMA", "NIFTY METAL", "NIFTY ENERGY", "NIFTY REALTY",
        "NIFTY MEDIA", "NIFTY PSU BANK", "NIFTY PRIVATE BANK", 
        "NIFTY HEALTHCARE",
    ]
    
    INDUSTRY = [
        "NIFTY FINANCIAL SERVICES", "NIFTY OIL & GAS", "NIFTY CONSUMER DURABLES",
        "NIFTY CAPITAL MARKETS", "NIFTY MIDSMALL HEALTHCARE",
        "NIFTY MIDSMALL FINANCIAL SERVICES", "NIFTY MIDSMALL IT & TELECOM",
        "NIFTY MIDSMALL INDIA CONSUMPTION", "NIFTY HOUSING",
        "NIFTY MOBILITY", "NIFTY NEW CONSUMER", "NIFTY MNC",
        "NIFTY INDIA TOURISM", "NIFTY DEFENCE", "NIFTY EV",
    ]
    
    FACTOR = [
        "NIFTY ALPHA 50", "NIFTY ALPHA LOW VOLATILITY 30",
        "NIFTY QUALITY 30", "NIFTY VALUE 50", "NIFTY MOMENTUM 50",
        "NIFTY MOMENTUM QUALITY 30", "NIFTY LOW VOLATILITY 50",
        "NIFTY HIGH BETA 50", "NIFTY DIVIDEND OPPORTUNITIES 50",
        "NIFTY GROWSECT 15", "NIFTY100 EQUAL WEIGHT", 
        "NIFTY100 LOW VOLATILITY 30", "NIFTY200 MOMENTUM 30",
        "NIFTY ALPHA QUALITY VALUE LV 30", "NIFTY200 ALPHA 30",
    ]
    
    THEMATIC = [
        "NIFTY CPSE", "NIFTY PSE", "NIFTY MNC", "NIFTY INFRASTRUCTURE",
        "NIFTY MANUFACTURING", "NIFTY SERVICES SECTOR", "NIFTY COMMODITIES",
        "NIFTY DIGITAL", "NIFTY INDIA CONSUMPTION", "NIFTY INDIA NEW AGE CONSUMPTION",
    ]
    
    rows = []
    for code in BROAD: rows.append((code, "broad"))
    for code in SECTORAL: rows.append((code, "sectoral"))
    for code in INDUSTRY: rows.append((code, "industry"))
    for code in FACTOR: rows.append((code, "factor"))
    for code in THEMATIC: rows.append((code, "thematic"))
    
    df = pl.DataFrame({
        "index_code": [r[0] for r in rows],
        "role": [r[1] for r in rows],
    })
    
    # Join with de_index_master for full metadata
    engine = get_engine()
    master_df = pl.read_database("""
        SELECT index_code, index_name, inception_date 
        FROM public.de_index_master
    """, engine)
    
    df = df.join(master_df, on="index_code", how="left")
    
    # Verify all curated codes exist in de_index_master
    missing = df.filter(pl.col("index_name").is_null())
    if len(missing) > 0:
        raise ValueError(f"Curated index codes not found in de_index_master: {missing}")
    
    # Add audit columns
    df = df.with_columns([
        pl.lit(None).cast(pl.Utf8).alias("linked_sector"),  # Filled below for sectoral
        pl.lit(Config.UNIVERSE_LOCK_DATE).str.to_date().alias("effective_from"),
        pl.lit(None).cast(pl.Date).alias("effective_to"),
    ])
    
    # For sectoral indices, link to atlas_sector_master.sector_name
    # Use a simple mapping for v0; v1 can refine
    sectoral_link_map = {
        "NIFTY BANK": "Bank", "NIFTY IT": "IT", "NIFTY FMCG": "FMCG",
        "NIFTY AUTO": "Auto", "NIFTY PHARMA": "Pharma", "NIFTY METAL": "Metal",
        "NIFTY ENERGY": "Energy", "NIFTY REALTY": "Realty", "NIFTY MEDIA": "Media",
        "NIFTY HEALTHCARE": "Healthcare",
    }
    df = df.with_columns(
        pl.col("index_code").map_elements(
            lambda code: sectoral_link_map.get(code), 
            return_dtype=pl.Utf8
        ).alias("linked_sector")
    )
    
    return df.select([
        "index_code", "index_name", "role", "linked_sector", 
        "inception_date", "effective_from", "effective_to"
    ])

def populate_atlas_universe_indices():
    df = build_index_universe()
    assert len(df) == 75, f"Expected 75 indices, got {len(df)}"
    
    engine = get_engine()
    df.write_database("atlas.atlas_universe_indices", engine, if_table_exists="append")
    print(f"Populated atlas_universe_indices with {len(df)} rows")
```

**Step 5 — Implement `atlas/universe/funds.py`**

```python
def build_fund_universe() -> pl.DataFrame:
    """
    Equity, Regular plan, Growth option only.
    Categories: Large Cap, Mid Cap, Small Cap, Large & Midcap, Multi Cap, 
                Flexi Cap, ELSS, Sectoral/Thematic mapped to NSE sectors.
    Excludes: Hybrid, Debt, IDCW, Direct, Index funds, Solution-oriented, 
              Global, Novelty thematic.
    """
    engine = get_engine()
    
    query = """
    SELECT 
        m.mstar_id,
        m.scheme_name,
        m.amc,
        m.broad_category,
        m.category_name,
        m.plan_type,
        m.option_type,
        m.inception_date
    FROM public.de_mf_master m
    WHERE 
        m.broad_category = 'Equity'
        AND m.plan_type = 'Regular'
        AND m.option_type = 'Growth'
        AND m.category_name IN (
            'Large Cap Fund', 'Mid Cap Fund', 'Small Cap Fund',
            'Large & Mid Cap Fund', 'Multi Cap Fund', 'Flexi Cap Fund',
            'ELSS', 'Sectoral / Thematic Fund'
        )
        AND EXISTS (
            -- Must have NAV data
            SELECT 1 FROM public.de_mf_nav_daily n 
            WHERE n.mstar_id = m.mstar_id 
            LIMIT 1
        )
    ORDER BY m.amc, m.scheme_name
    """
    
    with engine.connect() as conn:
        df = pl.read_database(query, conn)
    
    # Excluded: Index funds, ETFs (we have separate ETF universe), Global, Solution-oriented
    # The query already filters most of these via category_name; spot-check for residuals
    df = df.filter(
        ~pl.col("scheme_name").str.to_uppercase().str.contains("INDEX FUND")
        & ~pl.col("scheme_name").str.to_uppercase().str.contains("GLOBAL")
        & ~pl.col("scheme_name").str.to_uppercase().str.contains("WORLD")
        & ~pl.col("scheme_name").str.to_uppercase().str.contains("RETIREMENT")
        & ~pl.col("scheme_name").str.to_uppercase().str.contains("CHILDREN")
        & ~pl.col("scheme_name").str.to_uppercase().str.contains("ESG")
    )
    
    # Map category to benchmark_code
    category_benchmark_map = {
        "Large Cap Fund": "NIFTY100",
        "Large & Mid Cap Fund": "NIFTY200",  # Or NIFTY100; doc allows either
        "Mid Cap Fund": "MIDCAP150",
        "Small Cap Fund": "SMALLCAP250",
        "Multi Cap Fund": "NIFTY500",
        "Flexi Cap Fund": "NIFTY500",
        "ELSS": "NIFTY500",
        "Sectoral / Thematic Fund": "NIFTY500",  # Default; per-fund refinement deferred to v1
    }
    
    df = df.with_columns([
        pl.col("category_name").map_elements(
            lambda cat: category_benchmark_map.get(cat, "NIFTY500"),
            return_dtype=pl.Utf8
        ).alias("benchmark_code"),
        pl.lit(Config.UNIVERSE_LOCK_DATE).str.to_date().alias("effective_from"),
        pl.lit(None).cast(pl.Date).alias("effective_to"),
    ])
    
    return df.select([
        "mstar_id", "scheme_name", "amc", "broad_category", "category_name",
        "plan_type", "option_type", "benchmark_code", "inception_date",
        "effective_from", "effective_to"
    ])

def populate_atlas_universe_funds():
    df = build_fund_universe()
    
    n = len(df)
    assert 350 <= n <= 500, f"Expected 350-500 funds, got {n}"
    
    engine = get_engine()
    df.write_database("atlas.atlas_universe_funds", engine, if_table_exists="append")
    print(f"Populated atlas_universe_funds with {n} rows")
    
    # Category distribution
    cat_counts = df.group_by("category_name").len().sort("len", descending=True)
    print("Category distribution:")
    print(cat_counts)
```

**Step 6 — Populate `atlas_benchmark_master`**

Hardcoded inserts per `02_DATABASE_SCHEMA.md` Section 2.6:

```python
def populate_atlas_benchmark_master():
    benchmarks = [
        ("NIFTY50", "Nifty 50", "user", "de_index_prices", "NIFTY 50"),
        ("NIFTY500", "Nifty 500", "user", "de_index_prices", "NIFTY 500"),
        ("MSCIWORLD", "MSCI World", "user", "de_global_prices", "URTH"),
        ("SP500", "S&P 500", "user", "de_global_prices", "^GSPC"),
        ("GOLD", "Gold (GOLDBEES proxy)", "user/numeraire", "de_etf_ohlcv", "GOLDBEES"),
        ("NIFTY100", "Nifty 100", "tier", "de_index_prices", "NIFTY 100"),
        ("NIFTY200", "Nifty 200", "tier", "de_index_prices", "NIFTY 200"),
        ("MIDCAP150", "Nifty Midcap 150", "tier", "de_index_prices", "NIFTY MIDCAP 150"),
        ("SMALLCAP250", "Nifty Smallcap 250", "tier", "de_index_prices", "NIFTY SMALLCAP 250"),
    ]
    
    df = pl.DataFrame(
        benchmarks, 
        schema=["benchmark_code", "benchmark_name", "benchmark_type", "source_table", "source_identifier"],
        orient="row",
    ).with_columns(pl.lit(True).alias("is_active"))
    
    engine = get_engine()
    df.write_database("atlas.atlas_benchmark_master", engine, if_table_exists="append")
    print(f"Populated atlas_benchmark_master with {len(df)} rows")
```

**Step 7 — Populate `atlas_fund_category_benchmark_map`**

```python
def populate_atlas_fund_category_benchmark_map():
    mapping = [
        ("Large Cap Fund", "NIFTY100"),
        ("Large & Mid Cap Fund", "NIFTY200"),
        ("Mid Cap Fund", "MIDCAP150"),
        ("Small Cap Fund", "SMALLCAP250"),
        ("Multi Cap Fund", "NIFTY500"),
        ("Flexi Cap Fund", "NIFTY500"),
        ("ELSS", "NIFTY500"),
        ("Sectoral / Thematic Fund", "NIFTY500"),
    ]
    
    df = pl.DataFrame(mapping, schema=["category_name", "benchmark_code"], orient="row")
    
    engine = get_engine()
    df.write_database("atlas.atlas_fund_category_benchmark_map", engine, if_table_exists="append")
    print(f"Populated atlas_fund_category_benchmark_map with {len(df)} rows")
```

**Step 8 — Populate `atlas_thresholds` from `04_THRESHOLD_CATALOG.md`**

Seed the 35 thresholds with their default values, allowed ranges, descriptions, and category labels. Every threshold must match the catalog exactly.

```python
def populate_atlas_thresholds():
    """
    Seed atlas_thresholds with the 35 default thresholds from 04_THRESHOLD_CATALOG.md.
    Each row also creates an audit entry in atlas_threshold_history with old_value=NULL
    (the seed insert).
    """
    thresholds = [
        # (key, default, min, max, category, methodology_section, units, description)
        # --- Pre-classification gates ---
        ("liquidity_min_traded_value_inr", 50_000_000, 10_000_000, 250_000_000,
         "gate", "3.3", "inr",
         "Minimum trailing 60-day median daily traded value for liquidity gate"),
        ("history_min_trading_days", 252, 180, 504,
         "gate", "3.3", "days",
         "Minimum trading days of OHLCV history before classification eligibility"),
        
        # --- RS classification ---
        ("rs_quintile_top", 0.80, 0.70, 0.90,
         "rs", "7.1", "pctile",
         "Top-quintile cutoff for RS percentile rank within tier"),
        ("rs_quintile_bottom", 0.20, 0.10, 0.30,
         "rs", "7.1", "pctile",
         "Bottom-quintile cutoff for RS percentile rank within tier"),
        
        # --- RS Momentum classification ---
        ("momentum_flat_band_pct", 0.02, 0.01, 0.05,
         "momentum", "7.2", "ratio",
         "Maximum |ema_10_ratio - 1| for Flat classification"),
        ("momentum_ema_convergence_pct", 0.01, 0.005, 0.03,
         "momentum", "7.2", "ratio",
         "Maximum |ema_10_ratio - ema_20_ratio| for Flat (EMAs converged)"),
        ("momentum_breakout_lookback_days", 20, 10, 50,
         "momentum", "7.2", "days",
         "Lookback window for ema_10 at high/low detection"),
        
        # --- Risk classification ---
        ("risk_extension_low_max_pct", 25, 15, 35,
         "risk", "7.3", "percent",
         "Maximum extension % for Low/Normal risk"),
        ("risk_extension_high_min_pct", 40, 30, 60,
         "risk", "7.3", "percent",
         "Minimum extension % for High risk"),
        ("risk_vol_ratio_low_max", 1.0, 0.80, 1.10,
         "risk", "7.3", "ratio",
         "Maximum vol_ratio_63 for Low risk"),
        ("risk_vol_ratio_normal_max", 1.25, 1.10, 1.50,
         "risk", "7.3", "ratio",
         "Maximum vol_ratio_63 for Normal risk"),
        ("risk_vol_ratio_high_min", 1.6, 1.4, 2.0,
         "risk", "7.3", "ratio",
         "Minimum vol_ratio_63 for High risk"),
        
        # --- Volume classification ---
        ("volume_accumulation_expansion_min", 1.2, 1.05, 1.5,
         "volume", "7.4", "ratio",
         "Minimum volume_expansion for Accumulation"),
        ("volume_accumulation_effort_min", 1.3, 1.1, 1.8,
         "volume", "7.4", "ratio",
         "Minimum effort_ratio_63 for Accumulation"),
        ("volume_distribution_effort_max", 0.8, 0.6, 0.9,
         "volume", "7.4", "ratio",
         "Maximum effort_ratio_63 for Distribution"),
        ("volume_heavy_distribution_effort_max", 0.6, 0.4, 0.7,
         "volume", "7.4", "ratio",
         "Maximum effort_ratio_63 for Heavy Distribution"),
        
        # --- Weinstein gate ---
        ("weinstein_slope_sigma_min", -0.5, -1.0, 0.0,
         "gate", "7.1", "sigma",
         "Minimum 30-week MA slope (σ-normalized) for flat-or-rising condition"),
        
        # --- Stage-1 base ---
        ("stage1_weak_weeks_min", 8, 6, 10,
         "rs", "7.1", "weeks",
         "Minimum weak-state weeks (out of last 10) for Stage-1 base qualification"),
        ("stage1_ma_flat_sigma_max", 0.5, 0.3, 1.0,
         "rs", "7.1", "sigma",
         "Maximum |30-week MA slope σ| for flat MA condition in Stage-1 base"),
        
        # --- Sector classification ---
        ("sector_overweight_participation_min_pct", 50, 35, 70,
         "sector", "10.5", "percent",
         "Minimum participation_RS for Overweight sector"),
        ("sector_underweight_participation_max_pct", 30, 20, 45,
         "sector", "10.5", "percent",
         "Maximum participation_RS for Underweight sector"),
        ("sector_avoid_participation_max_pct", 25, 15, 35,
         "sector", "10.5", "percent",
         "Maximum participation_RS for Avoid sector"),
        
        # --- Market regime ---
        ("regime_risk_on_breadth_min_pct", 60, 50, 75,
         "regime", "11.4", "percent",
         "Minimum pct_above_ema_50 for Risk-On regime"),
        ("regime_constructive_breadth_min_pct", 50, 40, 60,
         "regime", "11.4", "percent",
         "Minimum pct_above_ema_50 for Constructive regime"),
        ("regime_risk_off_breadth_max_pct", 40, 25, 50,
         "regime", "11.4", "percent",
         "Maximum pct_above_ema_50 for Risk-Off regime"),
        ("regime_risk_on_vix_max", 18, 14, 22,
         "regime", "11.4", "vix_points",
         "Maximum India VIX for Risk-On regime"),
        ("regime_constructive_vix_max", 22, 18, 28,
         "regime", "11.4", "vix_points",
         "Maximum India VIX for Constructive regime"),
        ("regime_cautious_vix_max", 28, 24, 35,
         "regime", "11.4", "vix_points",
         "Maximum India VIX for Cautious regime"),
        ("regime_near_200ema_band_pct", 2, 1, 5,
         "regime", "11.4", "percent",
         "Width of 'near EMA 200' band for Cautious regime trigger"),
        ("dislocation_vol_multiplier", 4.0, 2.5, 6.0,
         "regime", "11.5", "ratio",
         "Multiple of 252-day median vol above which dislocation activates"),
        
        # --- Mutual fund lenses ---
        ("fund_aligned_aum_min_pct", 70, 60, 85,
         "fund", "12.2", "percent",
         "Minimum AUM in Overweight/Neutral sectors for Aligned"),
        ("fund_avoid_aum_max_pct", 10, 5, 20,
         "fund", "12.2", "percent",
         "Maximum AUM in Avoid sectors for Aligned"),
        ("fund_strong_holdings_min_pct", 60, 50, 75,
         "fund", "12.3", "percent",
         "Minimum AUM in Leader/Strong/Emerging stocks for Strong-Holdings"),
        ("fund_weak_holdings_max_pct", 25, 15, 35,
         "fund", "12.3", "percent",
         "Maximum AUM in Weak/Laggard stocks for Decent classification"),
        
        # --- Decision engine ---
        ("entry_breakout_proximity_max_pct", 5, 2, 10,
         "decision", "13.3", "percent",
         "Maximum distance from 20-EMA (%) for breakout entry trigger"),
    ]
    
    assert len(thresholds) == 35, f"Expected 35 thresholds, got {len(thresholds)}"
    
    df = pl.DataFrame(
        thresholds,
        schema=["threshold_key", "default_value", "min_allowed", "max_allowed",
                "category", "methodology_section", "units", "description"],
        orient="row",
    ).with_columns([
        pl.col("default_value").alias("threshold_value"),  # Initial value = default
        pl.lit("system").alias("last_modified_by"),
        pl.lit(True).alias("is_active"),
    ])
    
    engine = get_engine()
    df.write_database("atlas.atlas_thresholds", engine, if_table_exists="append")
    
    # Audit: insert seed entries into atlas_threshold_history
    history_df = df.select([
        "threshold_key",
        pl.lit(None, dtype=pl.Float64).alias("old_value"),
        pl.col("threshold_value").alias("new_value"),
        pl.lit("system").alias("changed_by"),
        pl.lit("Initial seed at Atlas-M1").alias("change_reason"),
        pl.lit(False).alias("triggered_reclassify"),
    ])
    history_df.write_database("atlas.atlas_threshold_history", engine, if_table_exists="append")
    
    print(f"Populated atlas_thresholds with {len(df)} rows")
    print(f"Seeded atlas_threshold_history with {len(history_df)} initial entries")
```

**Step 9 — Implement `atlas/universe/lock.py` orchestration**

```python
from atlas.universe import sectors, stocks, etfs, indices, funds

def lock_universe():
    """
    Single entry point — runs all universe lock operations in correct dependency order.
    """
    print("=" * 60)
    print("Atlas Universe Lock — Starting")
    print(f"Lock date: {Config.UNIVERSE_LOCK_DATE}")
    print("=" * 60)
    
    # Order matters: sectors first (referenced by ETFs and indices)
    sectors.populate_atlas_sector_master()
    
    # Benchmarks before fund universe (FK dependency)
    populate_atlas_benchmark_master()
    populate_atlas_fund_category_benchmark_map()
    
    # Universes
    stocks.populate_atlas_universe_stocks()
    etfs.populate_atlas_universe_etfs()
    indices.populate_atlas_universe_indices()
    funds.populate_atlas_universe_funds()
    
    # Threshold catalog seed (35 thresholds from 04_THRESHOLD_CATALOG.md)
    populate_atlas_thresholds()
    
    print("=" * 60)
    print("Atlas Universe Lock — Complete")
    print("=" * 60)
```

**Step 10 — Run universe lock via `scripts/m1_run.py`**

```python
#!/usr/bin/env python3
"""
Atlas-M1 entry point.
Runs schema migrations and universe lock.
"""
import sys
from pathlib import Path

# Run migrations first (assume migration tool exists; otherwise raw psql)
# Then run universe lock
from atlas.universe.lock import lock_universe

if __name__ == "__main__":
    print("Atlas-M1 — Schema and Reference Data")
    print("Step 1: Verify migrations applied (check schema exists)")
    # ... migration verification ...
    
    print("Step 2: Lock universe")
    lock_universe()
    
    print("Atlas-M1 — Complete. Run validation: python -m atlas.validation.tier1_raw")
```

### 6.3 Phase C Definition of Done

- [ ] `atlas_sector_master` populated; row count between 18 and 25
- [ ] `atlas_benchmark_master` populated; row count = 9
- [ ] `atlas_fund_category_benchmark_map` populated; row count between 8 and 10
- [ ] `atlas_universe_stocks` populated; row count = exactly 750
- [ ] Tier distribution: ~100 Large, ~150 Mid, ~250 Small, ~250 Micro
- [ ] `atlas_universe_etfs` populated; row count = exactly 100
- [ ] `atlas_universe_indices` populated; row count = exactly 75
- [ ] `atlas_universe_funds` populated; row count between 350 and 500
- [ ] `atlas_thresholds` populated; row count = exactly 35
- [ ] `atlas_threshold_history` populated; row count = 35 (one seed entry per threshold)
- [ ] Every threshold's `default_value` equals its `threshold_value` at seed time
- [ ] Every threshold's `threshold_value` is within `[min_allowed, max_allowed]`
- [ ] All foreign key relationships hold (no orphan references)
- [ ] All effective_to columns are NULL (current rows)

---

## 7. Phase D — Validation

### 7.1 Goal

Run Tier 1 raw data validation, Tier 4 universe coverage check, Tier 5 production health for one run. Generate the M1 validation report.

### 7.2 Tier 1 — Raw Data Validation

Per `03_VALIDATION_FRAMEWORK.md` Section 2:

```python
def run_tier1_for_m1():
    """
    Cross-validate JIP Data Core values against external sources.
    Sample: 20 stocks × 30 dates = 600 pairs (and same for ETFs, indices).
    For Atlas-M1, this confirms the source data we'll soon compute on is sound.
    """
    # Implementation per validation framework Section 2.2
    # Result: validation results written to atlas_validation_results
    pass
```

For Atlas-M1, this is a *check* — not a transformation. We're confirming the JIP data we're about to use in Atlas-M2 is reliable.

### 7.3 Tier 4 — Universe Coverage Check

Per `03_VALIDATION_FRAMEWORK.md` Section 5.1 Category D:

```sql
-- Every universe row must have a valid identifier in JIP Data Core
SELECT COUNT(*) FROM atlas.atlas_universe_stocks u
LEFT JOIN public.de_instrument i ON i.id = u.instrument_id
WHERE i.id IS NULL;
-- Expected: 0

SELECT COUNT(*) FROM atlas.atlas_universe_etfs u
LEFT JOIN public.de_etf_master m ON m.ticker = u.ticker
WHERE m.ticker IS NULL;
-- Expected: 0

SELECT COUNT(*) FROM atlas.atlas_universe_indices u
LEFT JOIN public.de_index_master m ON m.index_code = u.index_code
WHERE m.index_code IS NULL;
-- Expected: 0

SELECT COUNT(*) FROM atlas.atlas_universe_funds u
LEFT JOIN public.de_mf_master m ON m.mstar_id = u.mstar_id
WHERE m.mstar_id IS NULL;
-- Expected: 0

-- Sector mapping coverage: every stock's sector must exist in atlas_sector_master
SELECT DISTINCT u.sector
FROM atlas.atlas_universe_stocks u
LEFT JOIN atlas.atlas_sector_master s ON s.sector_name = u.sector
WHERE s.sector_name IS NULL;
-- Expected: 0 rows returned
```

### 7.4 Tier 5 — Production Health (One-Run Pass)

Atlas-M1 doesn't yet have a nightly compute pipeline (that comes in Atlas-M2 onwards), but we can verify:

- All tables created without errors
- All reference data populated within expected row count ranges
- All constraints satisfied
- `atlas_run_log` can be written to (test entry inserted and queried)

### 7.5 Generate Validation Report

Per `03_VALIDATION_FRAMEWORK.md` Section 8, produce `docs/validation/validation_M1_<date>.md` with the standard template filled in.

### 7.6 Phase D Definition of Done

- [ ] Tier 1 cross-validation passes for stocks, ETFs, indices, MFs (≥95% pass rate per asset class)
- [ ] Tier 4 universe coverage check returns zero orphan rows for all 5 checks
- [ ] Tier 5 single-run pass completes (table integrity, reference completeness)
- [ ] `validation_M1_<date>.md` exists in `docs/validation/` and shows PASS status
- [ ] `atlas_validation_results` table has entries for every check run

---

## 8. Atlas-M1 Definition of Done

The milestone is complete when ALL of the following are true:

**Code:**
- [ ] Repository created with full directory structure per Section 11 of architecture doc
- [ ] All migration files (001–010) committed
- [ ] All universe builders (stocks, ETFs, indices, funds, sectors) committed
- [ ] `scripts/m1_run.py` executes successfully end-to-end
- [ ] All unit tests in `tests/unit/` pass

**Database:**
- [ ] `atlas` schema exists with all 28 tables
- [ ] All indexes and constraints created
- [ ] Three database roles created with correct permissions
- [ ] All 7 reference tables populated with correct row counts

**Validation:**
- [ ] Tier 1 raw data validation: PASS (≥95% pass rate)
- [ ] Tier 4 universe coverage: PASS (zero orphans)
- [ ] Tier 5 single-run health check: PASS
- [ ] Validation report committed to `docs/validation/`

**Sign-off:**
- [ ] Engineer (Claude Code): Build complete, validation report generated
- [ ] Architect (Nimish): Reviewed validation report; spot-checked row counts; verified universe matches expectations

The milestone is NOT complete based on "code compiles" or "tables exist." It is complete only when the validation report is committed and signed off.

---

## 9. Common Pitfalls (Read Before Building)

**1. Don't compute anything Layer 3.** Atlas-M1 is reference data only. Even if metric tables exist (created empty), do not write any rows to them. That's Atlas-M2.

**2. Don't modify JIP Data Core.** Even if you find data quality issues in `de_*` tables, escalate to JIP team. Never INSERT, UPDATE, DELETE on `de_*` from Atlas code.

**3. Don't substitute libraries silently.** If pandas-ta installation fails, do not fall back to a different MA library. Stop and report. Library discipline (Architecture Section 5.5) is non-negotiable.

**4. Don't skip the universe count assertions.** If `len(stocks) != 750`, raise an error and stop. Don't write 749 stocks "close enough." The universe must be exactly the locked size.

**5. Don't pre-compute anything for Atlas-M2.** Even if it would save time later. Phase boundaries matter. Atlas-M2 is a separate validation cycle.

**6. Don't skip the `effective_from` / `effective_to` columns.** They look unused in v0 but are the slowly-changing-dimension foundation for v1's quarterly universe refresh. Populate them per spec.

**7. Migration idempotence is mandatory.** Every migration must use `CREATE ... IF NOT EXISTS`. If a migration fails halfway, you must be able to re-run it without error.

**8. Sector taxonomy comes from data, not from code.** Do not hardcode the 12-sector list. Query `de_instrument.sector` and use whatever NSE actually returns. The list might be 19, 20, or 22 sectors.

**9. Watch for stale data in `de_etf_ohlcv`.** Some ETFs may have stopped trading. The 60-day median traded value query has `HAVING COUNT(*) >= 30` to filter those out. Don't skip this clause.

**10. Don't deploy with `CHANGE_ME_BEFORE_DEPLOY` passwords.** The migration scripts contain placeholders. Replace before any deployment, document the password management approach in README.

---

## 10. Open Questions

Document these in the validation report rather than guessing:

1. **What if `de_sector_mapping` is incomplete?** Currently expected to be populated for all sectors with NSE indices. If some sectors lack mappings, document and proceed (fallback benchmark = NIFTY 500 will apply).

2. **What if `de_mf_master.option_type` values aren't exactly "Growth"?** Variations like "Gr", "Growth Plan" exist in some funds. Filter logic may need fuzzy matching. Document actual filter result in validation report.

3. **What if Nifty Microcap 250 isn't in `de_index_constituents`?** The original PRD noted the microcap 250 may not exist as a tracked index. Fallback: use 60-day median traded value for tier classification (already in the build_stock_universe code path).

4. **Index code naming exact match issue?** NSE has subtle inconsistencies (e.g., "NIFTY 50" vs "NIFTY50"). Verify exact strings match between curated list and `de_index_master.index_code`.

---

## 11. What Comes Next

Atlas-M2 (Stock + ETF Metric Engine) builds on the locked universe to compute the four primitives daily. Atlas-M2 spec is delivered separately, after Atlas-M1 sign-off.

Atlas-M2 cannot start until Atlas-M1 validation report is signed off. Hard dependency.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** Atlas-M1 completion
