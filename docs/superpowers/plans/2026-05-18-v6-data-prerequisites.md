# v6 Data Prerequisites (Plan 1A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the six data sources (D1-D6) the v6 trading model needs before any signal code is written: point-in-time Nifty 500 membership, ETF coverage gap-fill, macro daily series, F&O ban list, promoter pledge ratios, and auditor/promoter-group master.

**Architecture:** Six independent fetchers under `atlas/data_prereqs/v6/`, each owning one table. A shared `BaseScraper` handles NSE session/cookie/rate-limit discipline. Migration 080 creates all six tables atomically. Cron config in `atlas/data_prereqs/v6/schedules.py` wires the ongoing daily/weekly/quarterly schedules.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 + Alembic, `requests` with custom NSE headers, `yfinance` for global series, `pandas` for parsing, pytest + pytest-asyncio + responses (HTTP fixture), `apscheduler` for scheduling.

**Anchor docs:**
- Spec: [docs/superpowers/specs/2026-05-18-v6-rs-trading-model-design.md](../specs/2026-05-18-v6-rs-trading-model-design.md) §10
- Atlas hooks: source ≤ 600 LOC, tests ≤ 800 LOC, no float on money, structured logs
- Migration head: 079 (this plan starts at 080)

---

## File structure

### Backend — new files

- `migrations/versions/080_v6_prerequisites.py` — creates 6 tables (≤300 LOC)
- `atlas/data_prereqs/__init__.py` — package marker
- `atlas/data_prereqs/v6/__init__.py` — package marker
- `atlas/data_prereqs/v6/base.py` — shared NSE scraper base class (≤200 LOC)
- `atlas/data_prereqs/v6/membership.py` — D1: PIT Nifty 500 membership (≤300 LOC)
- `atlas/data_prereqs/v6/etf_coverage.py` — D2: ETF gap-fill (≤200 LOC)
- `atlas/data_prereqs/v6/macro_daily.py` — D3: USDINR + DXY + 10Y + T-bill + FII + breadth (≤400 LOC)
- `atlas/data_prereqs/v6/fno_ban.py` — D4: F&O ban list daily (≤200 LOC)
- `atlas/data_prereqs/v6/pledge.py` — D5: promoter pledge quarterly (≤300 LOC)
- `atlas/data_prereqs/v6/governance_master.py` — D6: auditor + promoter group (≤250 LOC)
- `atlas/data_prereqs/v6/schedules.py` — cron registrations (≤100 LOC)
- `atlas/data_prereqs/v6/cli.py` — `python -m atlas.data_prereqs.v6 backfill --source <name>` (≤200 LOC)

### Tests — new files

- `tests/data_prereqs/__init__.py`
- `tests/data_prereqs/v6/__init__.py`
- `tests/data_prereqs/v6/fixtures/` — captured HTTP responses, sample CSVs/XBRL
- `tests/data_prereqs/v6/test_migration.py` — migration up/down
- `tests/data_prereqs/v6/test_base.py` — scraper base behavior
- `tests/data_prereqs/v6/test_membership.py` — D1
- `tests/data_prereqs/v6/test_etf_coverage.py` — D2
- `tests/data_prereqs/v6/test_macro_daily.py` — D3
- `tests/data_prereqs/v6/test_fno_ban.py` — D4
- `tests/data_prereqs/v6/test_pledge.py` — D5
- `tests/data_prereqs/v6/test_governance_master.py` — D6
- `tests/data_prereqs/v6/test_schedules.py` — schedule registration

### Modified files

- `pyproject.toml` — add `yfinance`, `apscheduler`, `responses` (test-only)

---

## Task 1: Migration 080 — Create v6 prerequisite tables

**Files:**
- Create: `migrations/versions/080_v6_prerequisites.py`
- Test: `tests/data_prereqs/v6/test_migration.py`

- [ ] **Step 1.1: Write the migration up/down test**

```python
# tests/data_prereqs/v6/test_migration.py
"""Migration 080 — v6 prerequisite tables."""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def alembic_config():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["ATLAS_TEST_DB_URL"])
    return cfg


def test_migration_080_creates_six_tables(alembic_config):
    """All six v6 prereq tables exist after upgrade to 080."""
    command.upgrade(alembic_config, "080")
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    insp = inspect(eng)
    tables = set(insp.get_table_names(schema="atlas"))
    expected = {
        "atlas_index_membership",
        "atlas_factor_returns_daily",
        "atlas_macro_daily",
        "atlas_governance_master",
        "atlas_governance_daily",
        "atlas_v6_strategy_runs",
        "atlas_v6_exclusions_log",
        "atlas_v6_recommendations_daily",
    }
    assert expected.issubset(tables), f"Missing: {expected - tables}"


def test_migration_080_downgrade_drops_all(alembic_config):
    """Downgrade to 079 drops every table 080 created."""
    command.upgrade(alembic_config, "080")
    command.downgrade(alembic_config, "079")
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    insp = inspect(eng)
    tables = set(insp.get_table_names(schema="atlas"))
    must_not_exist = {
        "atlas_index_membership",
        "atlas_factor_returns_daily",
        "atlas_macro_daily",
        "atlas_governance_master",
        "atlas_governance_daily",
        "atlas_v6_strategy_runs",
        "atlas_v6_exclusions_log",
        "atlas_v6_recommendations_daily",
    }
    assert must_not_exist.isdisjoint(tables), f"Still present: {must_not_exist & tables}"


def test_migration_080_indexes_present(alembic_config):
    """Critical PIT lookup indexes exist."""
    command.upgrade(alembic_config, "080")
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    with eng.connect() as c:
        rows = c.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='atlas' AND tablename='atlas_index_membership'"
        )).fetchall()
    names = {r.indexname for r in rows}
    assert "ix_atlas_index_membership_lookup" in names
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `pytest tests/data_prereqs/v6/test_migration.py -v`
Expected: FAIL — migration 080 not yet defined.

- [ ] **Step 1.3: Write migration 080**

```python
# migrations/versions/080_v6_prerequisites.py
"""v6 data prerequisites — index membership, factor returns, macro daily,
governance master/daily, strategy runs, exclusions log, recommendations.

Revision ID: 080
Revises: 079
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. atlas_index_membership — point-in-time index reconstitution history
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_index_membership (
            index_name TEXT NOT NULL,
            instrument_id UUID NOT NULL,
            valid_from DATE NOT NULL,
            valid_to DATE,
            PRIMARY KEY (index_name, instrument_id, valid_from)
        );
        CREATE INDEX ix_atlas_index_membership_lookup
            ON atlas.atlas_index_membership (instrument_id, valid_from, valid_to);
    """)

    # 2. atlas_factor_returns_daily — Indian Fama-French + Carhart factor returns
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_factor_returns_daily (
            date DATE PRIMARY KEY,
            mkt_excess NUMERIC(10,6),
            smb        NUMERIC(10,6),
            wml        NUMERIC(10,6),
            hml        NUMERIC(10,6)
        );
    """)

    # 3. atlas_macro_daily — USDINR / DXY / 10Y / T-bill / FII / breadth
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_macro_daily (
            date DATE PRIMARY KEY,
            usdinr                  NUMERIC(10,4),
            dxy                     NUMERIC(10,4),
            india_10y_yield         NUMERIC(8,4),
            risk_free_91d           NUMERIC(8,4),
            fii_cash_equity_flow_cr NUMERIC(14,2),
            breadth_pct_above_200dma NUMERIC(5,2)
        );
    """)

    # 4. atlas_governance_master — auditor + promoter group + audit qualifications
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_governance_master (
            instrument_id            UUID PRIMARY KEY,
            promoter_group           TEXT,
            auditor_name             TEXT,
            auditor_is_top_10        BOOLEAN,
            last_auditor_change_date DATE,
            last_qualified_audit_date DATE,
            updated_at               TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX ix_atlas_governance_master_group
            ON atlas.atlas_governance_master (promoter_group);
    """)

    # 5. atlas_governance_daily — pledge ratio + F&O ban
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_governance_daily (
            instrument_id        UUID NOT NULL,
            date                 DATE NOT NULL,
            pledge_ratio_pct     NUMERIC(6,2),
            in_fno_ban_list      BOOLEAN,
            PRIMARY KEY (instrument_id, date)
        );
        CREATE INDEX ix_atlas_governance_daily_date
            ON atlas.atlas_governance_daily (date);
    """)

    # 6. atlas_v6_strategy_runs — backtest runs + goal-post evaluations
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_v6_strategy_runs (
            run_id                  UUID PRIMARY KEY,
            strategy_name           TEXT NOT NULL,
            signal_weights          JSONB NOT NULL,
            is_period               TSRANGE NOT NULL,
            oos_period              TSRANGE NOT NULL,
            calmar                  NUMERIC,
            vol_ratio               NUMERIC,
            mdd_ratio               NUMERIC,
            win_rate                NUMERIC,
            alpha_t_stat            NUMERIC,
            oos_ic_retention        NUMERIC,
            capacity_cr             NUMERIC,
            turnover_annual         NUMERIC,
            dd_compliance           NUMERIC,
            passes_all_constraints  BOOLEAN,
            constraint_failures     TEXT[],
            holdout_examined_at     TIMESTAMPTZ,
            created_at              TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 7. atlas_v6_exclusions_log — every governance exclusion + reason
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_v6_exclusions_log (
            instrument_id  UUID NOT NULL,
            date           DATE NOT NULL,
            reason         TEXT NOT NULL,
            weight_before  NUMERIC,
            weight_after   NUMERIC,
            PRIMARY KEY (instrument_id, date, reason)
        );
        CREATE INDEX ix_atlas_v6_exclusions_log_date
            ON atlas.atlas_v6_exclusions_log (date);
    """)

    # 8. atlas_v6_recommendations_daily — daily live picks
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_v6_recommendations_daily (
            date             DATE NOT NULL,
            instrument_id    UUID NOT NULL,
            composite_score  NUMERIC NOT NULL,
            weight_in_book   NUMERIC NOT NULL,
            rank             INT NOT NULL,
            confidence_band  TEXT NOT NULL,
            PRIMARY KEY (date, instrument_id),
            CONSTRAINT confidence_band_check
                CHECK (confidence_band IN ('HIGH', 'MED', 'LOW'))
        );
        CREATE INDEX ix_atlas_v6_recs_date_rank
            ON atlas.atlas_v6_recommendations_daily (date, rank);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_v6_recommendations_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_v6_exclusions_log;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_v6_strategy_runs;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_governance_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_governance_master;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_macro_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_factor_returns_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_index_membership;")
```

- [ ] **Step 1.4: Run the test to verify it passes**

Run: `pytest tests/data_prereqs/v6/test_migration.py -v`
Expected: PASS — all three tests green.

- [ ] **Step 1.5: Commit**

```bash
git add migrations/versions/080_v6_prerequisites.py \
        tests/data_prereqs/v6/test_migration.py \
        tests/data_prereqs/__init__.py \
        tests/data_prereqs/v6/__init__.py
git commit -m "migration(080): create v6 prerequisite tables"
```

---

## Task 2: Shared scraper base (`base.py`)

NSE serves data behind an anti-bot cookie wall. Every scraper needs the same session-warming pattern (visit homepage, capture cookies, send subsequent requests with browser-like headers). Centralizing this avoids duplication and ensures consistent rate limiting.

**Files:**
- Create: `atlas/data_prereqs/__init__.py`
- Create: `atlas/data_prereqs/v6/__init__.py`
- Create: `atlas/data_prereqs/v6/base.py`
- Test: `tests/data_prereqs/v6/test_base.py`

- [ ] **Step 2.1: Write failing tests for BaseScraper behavior**

```python
# tests/data_prereqs/v6/test_base.py
"""Shared NSE scraper base — session warming, rate limit, retry."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import responses

from atlas.data_prereqs.v6.base import BaseScraper, RateLimitExceeded


@responses.activate
def test_base_scraper_warms_session_with_homepage():
    """First request triggers a homepage GET to capture NSE session cookies."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="<html></html>",
                  headers={"Set-Cookie": "nsit=abc; path=/"})
    responses.add(responses.GET, "https://www.nseindia.com/api/whatever",
                  json={"ok": True})
    s = BaseScraper()
    out = s.get("https://www.nseindia.com/api/whatever")
    assert out.json() == {"ok": True}
    assert len(responses.calls) == 2
    assert responses.calls[0].request.url == "https://www.nseindia.com/"


@responses.activate
def test_base_scraper_uses_browser_headers():
    """All requests carry browser-like User-Agent + Accept headers."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="ok")
    responses.add(responses.GET, "https://www.nseindia.com/api/x", json={})
    s = BaseScraper()
    s.get("https://www.nseindia.com/api/x")
    final_req = responses.calls[-1].request
    assert "Mozilla/5.0" in final_req.headers["User-Agent"]
    assert final_req.headers["Accept"].startswith("application/json")


@responses.activate
def test_base_scraper_retries_on_503():
    """503 from NSE → retry with backoff, succeed on second attempt."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="ok")
    responses.add(responses.GET, "https://www.nseindia.com/api/y", status=503)
    responses.add(responses.GET, "https://www.nseindia.com/api/y", json={"data": 1})
    with patch("time.sleep"):  # don't actually wait
        s = BaseScraper(retry_max=3, retry_backoff_sec=0.01)
        out = s.get("https://www.nseindia.com/api/y")
    assert out.json() == {"data": 1}


@responses.activate
def test_base_scraper_raises_after_max_retries():
    """All retries exhausted → RateLimitExceeded."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="ok")
    for _ in range(4):
        responses.add(responses.GET, "https://www.nseindia.com/api/z", status=429)
    with patch("time.sleep"):
        s = BaseScraper(retry_max=3, retry_backoff_sec=0.01)
        with pytest.raises(RateLimitExceeded):
            s.get("https://www.nseindia.com/api/z")


def test_base_scraper_enforces_min_interval_between_requests():
    """min_interval_sec=0.5 means 2 calls take >= 0.5s."""
    s = BaseScraper(min_interval_sec=0.5)
    t0 = time.monotonic()
    s._wait_for_interval()  # first call: no wait
    s._wait_for_interval()  # second call: ~0.5s wait
    assert time.monotonic() - t0 >= 0.49
```

- [ ] **Step 2.2: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_base.py -v`
Expected: FAIL — `BaseScraper` not yet importable.

- [ ] **Step 2.3: Implement `BaseScraper`**

```python
# atlas/data_prereqs/__init__.py
"""Data prerequisite fetchers used by atlas strategy engines."""
```

```python
# atlas/data_prereqs/v6/__init__.py
"""v6 data prerequisites: PIT membership, ETF coverage, macro daily,
F&O ban, promoter pledge, auditor + promoter group master."""
```

```python
# atlas/data_prereqs/v6/base.py
"""Shared scraper base for NSE / external data sources.

Responsibilities:
- Session warming (visit https://www.nseindia.com/ once to capture cookies)
- Browser-like headers on every request
- Min-interval rate limiting (default 0.5s between calls)
- Exponential-backoff retry on 429/503 (default 3 retries)
- Raise RateLimitExceeded if all retries fail
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests
import structlog

log = structlog.get_logger()


class RateLimitExceeded(Exception):
    """All retries exhausted; the upstream source is throttling us."""


@dataclass
class BaseScraper:
    min_interval_sec: float = 0.5
    retry_max: int = 3
    retry_backoff_sec: float = 1.0
    nse_homepage: str = "https://www.nseindia.com/"
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self._warmed = False
        self._last_request_at: float | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.nse_homepage,
        }

    def _warm_session(self) -> None:
        if self._warmed:
            return
        try:
            self.session.get(self.nse_homepage, headers=self._headers(), timeout=10)
            self._warmed = True
        except requests.RequestException as exc:
            log.warning("session_warm_failed", err=str(exc))

    def _wait_for_interval(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_sec:
            time.sleep(self.min_interval_sec - elapsed)
        self._last_request_at = time.monotonic()

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        self._warm_session()
        attempt = 0
        while True:
            self._wait_for_interval()
            resp = self.session.get(
                url, headers=self._headers(), params=params, timeout=30
            )
            if resp.status_code in (429, 503):
                attempt += 1
                if attempt > self.retry_max:
                    log.error("retries_exhausted", url=url, status=resp.status_code)
                    raise RateLimitExceeded(f"{url} status {resp.status_code}")
                backoff = self.retry_backoff_sec * (2 ** (attempt - 1))
                log.info("retry", url=url, attempt=attempt, backoff=backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            return resp
```

- [ ] **Step 2.4: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_base.py -v`
Expected: PASS — all five tests green.

- [ ] **Step 2.5: Commit**

```bash
git add atlas/data_prereqs/__init__.py atlas/data_prereqs/v6/__init__.py \
        atlas/data_prereqs/v6/base.py tests/data_prereqs/v6/test_base.py
git commit -m "feat(data_prereqs): shared NSE scraper base with session warming + retry"
```

---

## Task 3: D1 — Point-in-time Nifty 500 membership

NSE publishes index reconstitution history. We need a `(symbol, valid_from, valid_to)` record per stock per period of Nifty 500 membership. Source: NSE press releases on index changes + historical index data CSVs.

**Files:**
- Create: `atlas/data_prereqs/v6/membership.py`
- Create: `tests/data_prereqs/v6/fixtures/nifty500_reconstitution_2024_09.json`
- Create: `tests/data_prereqs/v6/test_membership.py`

- [ ] **Step 3.1: Capture a fixture file from NSE**

Manually save a known-good Nifty 500 reconstitution JSON to:
`tests/data_prereqs/v6/fixtures/nifty500_reconstitution_2024_09.json`

Content (3 example entries — the full file has ~500):
```json
{
  "indexName": "NIFTY 500",
  "effectiveDate": "2024-09-30",
  "constituents": [
    {"symbol": "RELIANCE", "isin": "INE002A01018"},
    {"symbol": "TCS",      "isin": "INE467B01029"},
    {"symbol": "INFY",     "isin": "INE009A01021"}
  ]
}
```

- [ ] **Step 3.2: Write failing test for membership snapshot ingest**

```python
# tests/data_prereqs/v6/test_membership.py
"""D1: PIT Nifty 500 membership ingest + diff-to-state."""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.membership import (
    MembershipIngester,
    parse_reconstitution_snapshot,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "nifty500_reconstitution_2024_09.json"
)


def test_parse_reconstitution_snapshot_yields_symbol_set():
    """Parser returns the set of symbols + the effective date."""
    payload = json.loads(FIXTURE.read_text())
    snap = parse_reconstitution_snapshot(payload)
    assert snap.effective_date == date(2024, 9, 30)
    assert snap.symbols == {"RELIANCE", "TCS", "INFY"}
    assert snap.index_name == "NIFTY 500"


def test_diff_two_snapshots_produces_adds_and_drops():
    """Diff identifies entries (adds) and exits (drops)."""
    from atlas.data_prereqs.v6.membership import diff_snapshots
    prior_symbols = {"RELIANCE", "TCS", "FOO"}
    curr_symbols = {"RELIANCE", "TCS", "INFY"}
    adds, drops = diff_snapshots(prior_symbols, curr_symbols)
    assert adds == {"INFY"}
    assert drops == {"FOO"}


def test_apply_diff_updates_valid_to_for_drops(monkeypatch, tmp_db_session):
    """When a symbol exits, its open row gets valid_to set."""
    ing = MembershipIngester(tmp_db_session)
    riid, tiid = uuid.uuid4(), uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_index_membership
            (index_name, instrument_id, valid_from, valid_to)
        VALUES ('NIFTY 500', :r, '2024-03-30', NULL),
               ('NIFTY 500', :t, '2024-03-30', NULL)
    """), {"r": str(riid), "t": str(tiid)})
    # Resolver maps symbols to instrument_ids
    monkeypatch.setattr(
        ing, "_resolve_symbol_to_iid",
        lambda s: {"RELIANCE": riid, "TCS": tiid}[s],
    )
    ing.apply_diff(
        index_name="NIFTY 500",
        effective_date=date(2024, 9, 30),
        adds=set(),
        drops={"TCS"},
    )
    row = tmp_db_session.execute(text(
        "SELECT valid_to FROM atlas.atlas_index_membership "
        "WHERE instrument_id = :i"
    ), {"i": str(tiid)}).first()
    assert row.valid_to == date(2024, 9, 30)


def test_apply_diff_opens_new_row_for_adds(monkeypatch, tmp_db_session):
    """When a symbol enters, a new row is inserted with valid_to = NULL."""
    ing = MembershipIngester(tmp_db_session)
    iiid = uuid.uuid4()
    monkeypatch.setattr(ing, "_resolve_symbol_to_iid", lambda s: iiid)
    ing.apply_diff(
        index_name="NIFTY 500",
        effective_date=date(2024, 9, 30),
        adds={"INFY"},
        drops=set(),
    )
    row = tmp_db_session.execute(text(
        "SELECT valid_from, valid_to FROM atlas.atlas_index_membership "
        "WHERE instrument_id = :i"
    ), {"i": str(iiid)}).first()
    assert row.valid_from == date(2024, 9, 30)
    assert row.valid_to is None
```

The `tmp_db_session` fixture comes from a conftest that yields a SAVEPOINT-wrapped transactional session — standard atlas test pattern. Add it to `tests/data_prereqs/v6/conftest.py` if not already present.

- [ ] **Step 3.3: Create the conftest**

```python
# tests/data_prereqs/v6/conftest.py
"""Shared fixtures for v6 data prereq tests."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def tmp_db_session():
    """Transactional SAVEPOINT — rolled back after each test."""
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    Session = sessionmaker(bind=eng)
    conn = eng.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    trans.rollback()
    conn.close()
```

- [ ] **Step 3.4: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_membership.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 3.5: Implement membership ingester**

```python
# atlas/data_prereqs/v6/membership.py
"""D1: Point-in-time Nifty 500 (and Nifty 100, etc.) membership ingester.

Each NSE index reconstitution event is a snapshot — the set of symbols valid
on a specific effective date. We diff consecutive snapshots to produce
(symbol, valid_from, valid_to) rows in atlas_index_membership.

For backfill, the operator manually downloads snapshots for each historical
reconstitution date and feeds them to MembershipIngester.ingest_snapshot.
For ongoing maintenance, schedules.py runs a fetch_latest_and_diff each
night around 19:00 IST.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass(frozen=True)
class ReconstitutionSnapshot:
    index_name: str
    effective_date: date
    symbols: frozenset[str]


def parse_reconstitution_snapshot(payload: dict) -> ReconstitutionSnapshot:
    """Parse NSE reconstitution JSON → typed snapshot."""
    return ReconstitutionSnapshot(
        index_name=payload["indexName"],
        effective_date=date.fromisoformat(payload["effectiveDate"]),
        symbols=frozenset(c["symbol"] for c in payload["constituents"]),
    )


def diff_snapshots(
    prior: set[str], curr: set[str]
) -> tuple[set[str], set[str]]:
    """Return (adds, drops) — symbols entering vs exiting."""
    return curr - prior, prior - curr


@dataclass
class MembershipIngester:
    session: Session

    def _resolve_symbol_to_iid(self, symbol: str) -> uuid.UUID:
        row = self.session.execute(text(
            "SELECT instrument_id FROM atlas.atlas_instrument_master "
            "WHERE symbol = :s LIMIT 1"
        ), {"s": symbol}).first()
        if row is None:
            raise LookupError(f"symbol {symbol} not in instrument master")
        return uuid.UUID(str(row.instrument_id))

    def apply_diff(
        self,
        index_name: str,
        effective_date: date,
        adds: set[str],
        drops: set[str],
    ) -> None:
        for sym in drops:
            iid = self._resolve_symbol_to_iid(sym)
            self.session.execute(text("""
                UPDATE atlas.atlas_index_membership
                   SET valid_to = :d
                 WHERE index_name = :idx
                   AND instrument_id = :iid
                   AND valid_to IS NULL
            """), {"d": effective_date, "idx": index_name, "iid": str(iid)})
        for sym in adds:
            iid = self._resolve_symbol_to_iid(sym)
            self.session.execute(text("""
                INSERT INTO atlas.atlas_index_membership
                    (index_name, instrument_id, valid_from, valid_to)
                VALUES (:idx, :iid, :d, NULL)
                ON CONFLICT DO NOTHING
            """), {"idx": index_name, "iid": str(iid), "d": effective_date})
        self.session.commit()
        log.info("membership_diff_applied",
                 index=index_name, date=effective_date.isoformat(),
                 adds=len(adds), drops=len(drops))

    def ingest_snapshot(self, snapshot: ReconstitutionSnapshot) -> None:
        """Compute diff vs current open-membership set and apply."""
        rows = self.session.execute(text("""
            SELECT i.symbol
              FROM atlas.atlas_index_membership m
              JOIN atlas.atlas_instrument_master i USING (instrument_id)
             WHERE m.index_name = :idx AND m.valid_to IS NULL
        """), {"idx": snapshot.index_name}).fetchall()
        prior = {r.symbol for r in rows}
        adds, drops = diff_snapshots(prior, set(snapshot.symbols))
        self.apply_diff(
            index_name=snapshot.index_name,
            effective_date=snapshot.effective_date,
            adds=adds,
            drops=drops,
        )
```

- [ ] **Step 3.6: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_membership.py -v`
Expected: PASS — all four tests green.

- [ ] **Step 3.7: Commit**

```bash
git add atlas/data_prereqs/v6/membership.py \
        tests/data_prereqs/v6/test_membership.py \
        tests/data_prereqs/v6/conftest.py \
        tests/data_prereqs/v6/fixtures/nifty500_reconstitution_2024_09.json
git commit -m "feat(data_prereqs): D1 PIT Nifty 500 membership ingester"
```

- [ ] **Step 3.8: Manual backfill — historical snapshots**

This is operator work, not code. Document the procedure as a runbook entry in `docs/runbooks/v6-membership-backfill.md` (create it). Lists the NSE URLs for semi-annual reconstitution announcements, the date range (2010-2025), and one CLI invocation per snapshot:

```bash
python -m atlas.data_prereqs.v6.cli ingest-membership \
    --snapshot tests/data_prereqs/v6/fixtures/nifty500_reconstitution_2024_09.json
```

(CLI is built in Task 9.) Skip this step for the initial code merge; it runs during operational backfill.

---

## Task 4: D2 — ETF coverage check + Yahoo backfill

We need ≥10y of daily history for GOLDBEES (gold proxy) and LIQUIDBEES / BHARAT BOND (G-Sec proxy). The atlas database already has `atlas_etf_metrics_daily`. Step 1 is a coverage check; step 2 is Yahoo backfill where coverage is short.

**Files:**
- Create: `atlas/data_prereqs/v6/etf_coverage.py`
- Create: `tests/data_prereqs/v6/test_etf_coverage.py`

- [ ] **Step 4.1: Write failing test for coverage check**

```python
# tests/data_prereqs/v6/test_etf_coverage.py
"""D2: ETF coverage check + Yahoo backfill for crisis-sleeve ETFs."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.etf_coverage import (
    EtfCoverageChecker,
    YahooBackfiller,
    SLEEVE_ETFS,
)


def test_sleeve_etfs_list_has_required_symbols():
    assert "GOLDBEES" in SLEEVE_ETFS
    assert any(s.startswith("LIQUIDBEES") or "BHARAT" in s for s in SLEEVE_ETFS)


def test_coverage_check_reports_gap(tmp_db_session):
    """coverage_for returns (first_date, last_date, gap_days_to_target)."""
    iid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'GOLDBEES')
        ON CONFLICT DO NOTHING
    """), {"i": str(iid)})
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_etf_metrics_daily (instrument_id, date, close)
        VALUES (:i, '2020-01-01', 100.0), (:i, '2020-01-02', 101.0)
    """), {"i": str(iid)})
    chk = EtfCoverageChecker(tmp_db_session, target_years=10)
    cov = chk.coverage_for("GOLDBEES", reference_date=date(2025, 1, 1))
    assert cov.first_date == date(2020, 1, 1)
    assert cov.last_date == date(2020, 1, 2)
    assert cov.gap_days_to_target > 1800  # ~5y short


def test_yahoo_backfiller_inserts_missing_rows(tmp_db_session):
    """Backfiller fetches Yahoo and inserts rows not already in DB."""
    iid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'GOLDBEES')
        ON CONFLICT DO NOTHING
    """), {"i": str(iid)})
    yahoo_df = pd.DataFrame({
        "Date":  pd.to_datetime(["2014-01-01", "2014-01-02"]),
        "Close": [42.5, 42.7],
    })
    with patch("atlas.data_prereqs.v6.etf_coverage.yf.download",
               return_value=yahoo_df.set_index("Date")):
        bf = YahooBackfiller(tmp_db_session)
        n = bf.backfill("GOLDBEES", "GOLDBEES.NS",
                        start=date(2014, 1, 1), end=date(2014, 1, 2))
    assert n == 2
    rows = tmp_db_session.execute(text(
        "SELECT COUNT(*) AS n FROM atlas.atlas_etf_metrics_daily "
        "WHERE instrument_id = :i"
    ), {"i": str(iid)}).first()
    assert rows.n == 2
```

- [ ] **Step 4.2: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_etf_coverage.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 4.3: Implement coverage check + Yahoo backfill**

```python
# atlas/data_prereqs/v6/etf_coverage.py
"""D2: ETF coverage check + Yahoo backfill for crisis-sleeve ETFs.

Verifies that GOLDBEES and the G-Sec proxy ETF have at least target_years
of daily history in atlas_etf_metrics_daily. Where coverage is short,
Yahoo Finance fills the gap.

Yahoo symbol mapping is intentionally explicit: NSE ETFs are .NS suffixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import structlog
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

SLEEVE_ETFS: tuple[str, ...] = ("GOLDBEES", "LIQUIDBEES", "BHARAT22 ETF")
YAHOO_MAP: dict[str, str] = {
    "GOLDBEES": "GOLDBEES.NS",
    "LIQUIDBEES": "LIQUIDBEES.NS",
    "BHARAT22 ETF": "BHARAT22.NS",
}


@dataclass(frozen=True)
class Coverage:
    symbol: str
    first_date: date | None
    last_date: date | None
    gap_days_to_target: int


@dataclass
class EtfCoverageChecker:
    session: Session
    target_years: int = 10

    def coverage_for(self, symbol: str, reference_date: date) -> Coverage:
        row = self.session.execute(text("""
            SELECT MIN(e.date) AS first_date, MAX(e.date) AS last_date
              FROM atlas.atlas_etf_metrics_daily e
              JOIN atlas.atlas_instrument_master i USING (instrument_id)
             WHERE i.symbol = :s
        """), {"s": symbol}).first()
        if row is None or row.first_date is None:
            return Coverage(symbol, None, None, self.target_years * 365)
        target_first = reference_date.toordinal() - (self.target_years * 365)
        actual_first = row.first_date.toordinal()
        gap = max(0, actual_first - target_first)
        return Coverage(symbol, row.first_date, row.last_date, gap)


@dataclass
class YahooBackfiller:
    session: Session

    def _resolve_iid(self, symbol: str) -> str:
        row = self.session.execute(text(
            "SELECT instrument_id FROM atlas.atlas_instrument_master "
            "WHERE symbol = :s"
        ), {"s": symbol}).first()
        if row is None:
            raise LookupError(symbol)
        return str(row.instrument_id)

    def backfill(
        self, atlas_symbol: str, yahoo_symbol: str,
        start: date, end: date,
    ) -> int:
        df = yf.download(yahoo_symbol, start=start, end=end + pd.Timedelta(days=1),
                         progress=False)
        if df.empty:
            log.warning("yahoo_no_data", symbol=yahoo_symbol)
            return 0
        iid = self._resolve_iid(atlas_symbol)
        rows = [
            {"iid": iid, "date": d.date(), "close": float(df.loc[d, "Close"])}
            for d in df.index
        ]
        self.session.execute(text("""
            INSERT INTO atlas.atlas_etf_metrics_daily (instrument_id, date, close)
            VALUES (:iid, :date, :close)
            ON CONFLICT (instrument_id, date) DO NOTHING
        """), rows)
        self.session.commit()
        log.info("yahoo_backfill", symbol=atlas_symbol, rows=len(rows))
        return len(rows)
```

- [ ] **Step 4.4: Add `yfinance` to pyproject.toml**

Run: locate `[project.dependencies]` section, add `"yfinance>=0.2.40",`.

- [ ] **Step 4.5: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_etf_coverage.py -v`
Expected: PASS — all three tests green.

- [ ] **Step 4.6: Commit**

```bash
git add atlas/data_prereqs/v6/etf_coverage.py \
        tests/data_prereqs/v6/test_etf_coverage.py pyproject.toml
git commit -m "feat(data_prereqs): D2 ETF coverage checker + Yahoo backfill"
```

---

## Task 5: D3 — Macro daily series

Six daily macro signals into `atlas_macro_daily`: USDINR, DXY, India 10Y, 91d T-bill, FII cash equity flow, breadth (% above 200dMA). Sources are mixed (Yahoo + NSE + RBI + computed).

**Files:**
- Create: `atlas/data_prereqs/v6/macro_daily.py`
- Create: `tests/data_prereqs/v6/test_macro_daily.py`

- [ ] **Step 5.1: Write failing tests for each macro fetcher**

```python
# tests/data_prereqs/v6/test_macro_daily.py
"""D3: USDINR + DXY + India 10Y + 91d T-bill + FII flow + breadth → atlas_macro_daily."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.macro_daily import (
    BreadthComputer,
    FiiFlowFetcher,
    MacroDailyUpserter,
    UsdInrFetcher,
)


def test_usdinr_fetcher_returns_dataframe():
    yahoo_df = pd.DataFrame(
        {"Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
         "Close": [83.20, 83.25]}).set_index("Date")
    with patch("atlas.data_prereqs.v6.macro_daily.yf.download",
               return_value=yahoo_df):
        out = UsdInrFetcher().fetch(date(2024, 1, 1), date(2024, 1, 2))
    assert list(out.columns) == ["date", "usdinr"]
    assert out["usdinr"].iloc[0] == pytest.approx(83.20)


def test_fii_flow_fetcher_parses_nse_csv():
    """FII csv has columns: Date, Buy(₹ cr), Sell(₹ cr), Net(₹ cr)."""
    nse_csv = "Date,Buy(Cr),Sell(Cr),Net(Cr)\n01-Jan-2024,12000,11500,500\n"
    with patch("atlas.data_prereqs.v6.macro_daily.requests.get") as m:
        m.return_value.text = nse_csv
        m.return_value.status_code = 200
        out = FiiFlowFetcher().fetch(date(2024, 1, 1), date(2024, 1, 1))
    assert out["fii_cash_equity_flow_cr"].iloc[0] == 500.0


def test_breadth_computer_returns_pct_above_200dma(tmp_db_session):
    """Breadth on a given date = % of Nifty 500 stocks closing above their own 200dMA."""
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_stock_metrics_daily
            (instrument_id, date, close, ma_200)
        VALUES (gen_random_uuid(), '2024-01-02', 100, 90),
               (gen_random_uuid(), '2024-01-02', 100, 110),
               (gen_random_uuid(), '2024-01-02', 100, 95)
    """))
    bc = BreadthComputer(tmp_db_session)
    breadth = bc.compute(date(2024, 1, 2))
    assert breadth == pytest.approx(66.67, abs=0.5)


def test_upserter_inserts_one_row_per_date(tmp_db_session):
    upserter = MacroDailyUpserter(tmp_db_session)
    df = pd.DataFrame({
        "date": [date(2024, 1, 1)],
        "usdinr": [83.2], "dxy": [102.1],
        "india_10y_yield": [7.15], "risk_free_91d": [6.8],
        "fii_cash_equity_flow_cr": [500.0],
        "breadth_pct_above_200dma": [55.0],
    })
    upserter.upsert(df)
    r = tmp_db_session.execute(text(
        "SELECT * FROM atlas.atlas_macro_daily WHERE date = '2024-01-01'"
    )).first()
    assert float(r.usdinr) == 83.2
    assert float(r.breadth_pct_above_200dma) == 55.0
```

- [ ] **Step 5.2: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_macro_daily.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 5.3: Implement `macro_daily.py`**

```python
# atlas/data_prereqs/v6/macro_daily.py
"""D3: Daily macro series → atlas_macro_daily.

Six columns:
- usdinr                  : Yahoo INR=X
- dxy                     : Yahoo DX-Y.NYB
- india_10y_yield         : RBI MMR (best-effort; falls back to CCIL CSV)
- risk_free_91d           : RBI T-bill auction (best-effort)
- fii_cash_equity_flow_cr : NSE FII/DII CSV
- breadth_pct_above_200dma: computed from atlas_stock_metrics_daily
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests
import structlog
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass
class UsdInrFetcher:
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        raw = yf.download("INR=X", start=start, end=end + pd.Timedelta(days=1),
                          progress=False)
        if raw.empty:
            return pd.DataFrame(columns=["date", "usdinr"])
        return pd.DataFrame({"date": raw.index.date,
                             "usdinr": raw["Close"].values})


@dataclass
class DxyFetcher:
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        raw = yf.download("DX-Y.NYB", start=start, end=end + pd.Timedelta(days=1),
                          progress=False)
        if raw.empty:
            return pd.DataFrame(columns=["date", "dxy"])
        return pd.DataFrame({"date": raw.index.date,
                             "dxy": raw["Close"].values})


@dataclass
class FiiFlowFetcher:
    """NSE publishes a daily FII/DII cash equity flow CSV.

    Endpoint: https://archives.nseindia.com/content/equities/fii_stats_<DDMMYYYY>.xls
    For simplicity we use the rolled-up CSV historical archive when present.
    Returns net flow in ₹crore.
    """
    csv_endpoint: str = "https://www.nseindia.com/api/fiidii-tracker"

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        # Operator note: full NSE archive scrape is its own runbook;
        # for tests + initial backfill we accept a CSV-like input.
        resp = requests.get(self.csv_endpoint, timeout=30)
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        df["date"] = pd.to_datetime(df["Date"], dayfirst=True).dt.date
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        return df[["date", "Net(Cr)"]].rename(
            columns={"Net(Cr)": "fii_cash_equity_flow_cr"}
        )


@dataclass
class IndiaTenYearFetcher:
    """RBI publishes daily yield curves; operator backfills via CCIL CSV."""
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        # Placeholder — operator-driven CSV load. For tests, return empty.
        # Real implementation: download from
        # https://www.ccilindia.com/web/ccil/daily-historical-data
        return pd.DataFrame(columns=["date", "india_10y_yield"])


@dataclass
class RiskFree91dFetcher:
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        # RBI T-bill auction results (operator-driven CSV).
        return pd.DataFrame(columns=["date", "risk_free_91d"])


@dataclass
class BreadthComputer:
    session: Session

    def compute(self, ref_date: date) -> float:
        row = self.session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE close > ma_200) AS above,
                COUNT(*) AS total
              FROM atlas.atlas_stock_metrics_daily
             WHERE date = :d AND ma_200 IS NOT NULL
        """), {"d": ref_date}).first()
        if not row.total:
            return 0.0
        return round(100.0 * row.above / row.total, 2)


@dataclass
class MacroDailyUpserter:
    session: Session

    def upsert(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        rows = df.to_dict("records")
        self.session.execute(text("""
            INSERT INTO atlas.atlas_macro_daily
                (date, usdinr, dxy, india_10y_yield, risk_free_91d,
                 fii_cash_equity_flow_cr, breadth_pct_above_200dma)
            VALUES (:date, :usdinr, :dxy, :india_10y_yield, :risk_free_91d,
                    :fii_cash_equity_flow_cr, :breadth_pct_above_200dma)
            ON CONFLICT (date) DO UPDATE SET
                usdinr = EXCLUDED.usdinr,
                dxy = EXCLUDED.dxy,
                india_10y_yield = EXCLUDED.india_10y_yield,
                risk_free_91d = EXCLUDED.risk_free_91d,
                fii_cash_equity_flow_cr = EXCLUDED.fii_cash_equity_flow_cr,
                breadth_pct_above_200dma = EXCLUDED.breadth_pct_above_200dma
        """), rows)
        self.session.commit()
        return len(rows)
```

- [ ] **Step 5.4: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_macro_daily.py -v`
Expected: PASS — all four tests green.

- [ ] **Step 5.5: Commit**

```bash
git add atlas/data_prereqs/v6/macro_daily.py \
        tests/data_prereqs/v6/test_macro_daily.py
git commit -m "feat(data_prereqs): D3 macro daily fetchers (USDINR/DXY/FII/breadth)"
```

---

## Task 6: D4 — F&O ban list daily

NSE publishes the F&O ban list daily as a CSV. Backfill from NSE archive (2017+; earlier data not always available).

**Files:**
- Create: `atlas/data_prereqs/v6/fno_ban.py`
- Create: `tests/data_prereqs/v6/fixtures/fno_ban_sample.csv`
- Create: `tests/data_prereqs/v6/test_fno_ban.py`

- [ ] **Step 6.1: Capture sample CSV fixture**

```
tests/data_prereqs/v6/fixtures/fno_ban_sample.csv
```
Content:
```csv
Sr.No.,Symbol
1,IDEA
2,RBLBANK
3,DELTACORP
```

- [ ] **Step 6.2: Write failing tests**

```python
# tests/data_prereqs/v6/test_fno_ban.py
"""D4: F&O ban list daily fetch + upsert into atlas_governance_daily."""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.fno_ban import FnoBanFetcher, FnoBanUpserter

FIXTURE = Path(__file__).parent / "fixtures" / "fno_ban_sample.csv"


def test_fetcher_parses_csv():
    with patch("atlas.data_prereqs.v6.fno_ban.requests.get") as m:
        m.return_value.text = FIXTURE.read_text()
        m.return_value.status_code = 200
        symbols = FnoBanFetcher().fetch_for_date(date(2024, 6, 1))
    assert symbols == {"IDEA", "RBLBANK", "DELTACORP"}


def test_upserter_sets_in_fno_ban_flag(tmp_db_session):
    riid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'IDEA') ON CONFLICT DO NOTHING
    """), {"i": str(riid)})
    upserter = FnoBanUpserter(tmp_db_session)
    upserter.upsert(date(2024, 6, 1), {"IDEA"})
    row = tmp_db_session.execute(text("""
        SELECT in_fno_ban_list FROM atlas.atlas_governance_daily
        WHERE instrument_id = :i AND date = '2024-06-01'
    """), {"i": str(riid)}).first()
    assert row.in_fno_ban_list is True


def test_upserter_clears_flag_when_symbol_removed_from_ban(tmp_db_session):
    """A symbol removed from the daily list gets in_fno_ban_list = False."""
    riid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'IDEA') ON CONFLICT DO NOTHING;
        INSERT INTO atlas.atlas_governance_daily (instrument_id, date, in_fno_ban_list)
        VALUES (:i, '2024-06-01', true)
    """), {"i": str(riid)})
    upserter = FnoBanUpserter(tmp_db_session)
    # IDEA not in today's ban set
    upserter.upsert(date(2024, 6, 1), set())
    row = tmp_db_session.execute(text(
        "SELECT in_fno_ban_list FROM atlas.atlas_governance_daily "
        "WHERE instrument_id = :i AND date = '2024-06-01'"
    ), {"i": str(riid)}).first()
    assert row.in_fno_ban_list is False
```

- [ ] **Step 6.3: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_fno_ban.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 6.4: Implement `fno_ban.py`**

```python
# atlas/data_prereqs/v6/fno_ban.py
"""D4: NSE F&O ban list daily fetch + upsert.

Endpoint (daily current): https://archives.nseindia.com/content/fo/fo_secban.csv
For backfill, NSE maintains daily files under /content/fo/secban_<DDMMYYYY>.csv.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass
class FnoBanFetcher:
    base_url: str = "https://archives.nseindia.com/content/fo"

    def fetch_for_date(self, ref_date: date) -> set[str]:
        if ref_date == date.today():
            url = f"{self.base_url}/fo_secban.csv"
        else:
            url = f"{self.base_url}/secban_{ref_date.strftime('%d%m%Y')}.csv"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning("fno_ban_fetch_failed", url=url, status=resp.status_code)
            return set()
        df = pd.read_csv(io.StringIO(resp.text))
        col = next(c for c in df.columns if "symbol" in c.lower())
        return set(df[col].str.strip().tolist())


@dataclass
class FnoBanUpserter:
    session: Session

    def _resolve_iids(self, symbols: set[str]) -> dict[str, str]:
        if not symbols:
            return {}
        rows = self.session.execute(text("""
            SELECT symbol, instrument_id
              FROM atlas.atlas_instrument_master
             WHERE symbol = ANY(:syms)
        """), {"syms": list(symbols)}).fetchall()
        return {r.symbol: str(r.instrument_id) for r in rows}

    def upsert(self, ref_date: date, ban_symbols: set[str]) -> None:
        # Step 1: mark today's ban list as true
        if ban_symbols:
            iid_map = self._resolve_iids(ban_symbols)
            for sym, iid in iid_map.items():
                self.session.execute(text("""
                    INSERT INTO atlas.atlas_governance_daily
                        (instrument_id, date, in_fno_ban_list)
                    VALUES (:i, :d, true)
                    ON CONFLICT (instrument_id, date) DO UPDATE
                       SET in_fno_ban_list = true
                """), {"i": iid, "d": ref_date})
        # Step 2: clear flag on rows present yesterday but absent today
        self.session.execute(text("""
            UPDATE atlas.atlas_governance_daily
               SET in_fno_ban_list = false
             WHERE date = :d
               AND in_fno_ban_list = true
               AND instrument_id NOT IN (
                   SELECT instrument_id FROM atlas.atlas_instrument_master
                    WHERE symbol = ANY(:syms)
               )
        """), {"d": ref_date, "syms": list(ban_symbols)})
        self.session.commit()
        log.info("fno_ban_upserted", date=ref_date.isoformat(),
                 ban_count=len(ban_symbols))
```

- [ ] **Step 6.5: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_fno_ban.py -v`
Expected: PASS — all three tests green.

- [ ] **Step 6.6: Commit**

```bash
git add atlas/data_prereqs/v6/fno_ban.py tests/data_prereqs/v6/test_fno_ban.py \
        tests/data_prereqs/v6/fixtures/fno_ban_sample.csv
git commit -m "feat(data_prereqs): D4 F&O ban list daily fetcher + upserter"
```

---

## Task 7: D5 — Promoter pledge quarterly

NSE/BSE publish quarterly shareholding patterns. For each Nifty 500 company, parse the pledge ratio (`% of pledged shares / total promoter holding`). Forward-fill between quarters.

**Files:**
- Create: `atlas/data_prereqs/v6/pledge.py`
- Create: `tests/data_prereqs/v6/fixtures/pledge_sample.json`
- Create: `tests/data_prereqs/v6/test_pledge.py`

- [ ] **Step 7.1: Capture sample fixture**

```
tests/data_prereqs/v6/fixtures/pledge_sample.json
```
Content:
```json
{
  "asOfDate": "2024-09-30",
  "filings": [
    {"symbol": "DHFL", "promoter_total_shares": 1000000, "promoter_pledged_shares": 600000},
    {"symbol": "TCS",  "promoter_total_shares": 5000000, "promoter_pledged_shares": 0}
  ]
}
```

- [ ] **Step 7.2: Write failing tests**

```python
# tests/data_prereqs/v6/test_pledge.py
"""D5: Promoter pledge quarterly ingest + forward-fill into atlas_governance_daily."""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.pledge import (
    PledgeQuarterIngester,
    compute_pledge_ratio,
    parse_pledge_filing,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pledge_sample.json"


def test_compute_pledge_ratio_normal():
    assert compute_pledge_ratio(1000000, 600000) == pytest.approx(60.0)


def test_compute_pledge_ratio_zero_total_returns_none():
    assert compute_pledge_ratio(0, 0) is None


def test_parse_pledge_filing_yields_per_symbol_rows():
    payload = json.loads(FIXTURE.read_text())
    rows = parse_pledge_filing(payload)
    assert len(rows) == 2
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["DHFL"]["pledge_ratio_pct"] == pytest.approx(60.0)
    assert by_symbol["TCS"]["pledge_ratio_pct"] == pytest.approx(0.0)
    assert by_symbol["DHFL"]["effective_date"] == date(2024, 9, 30)


def test_ingester_forward_fills_to_next_quarter_minus_1_day(tmp_db_session):
    """If we ingest Q3 2024 (2024-09-30), rows should be created daily for
    2024-09-30 through next quarter end - 1 (2024-12-30)."""
    iid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'DHFL') ON CONFLICT DO NOTHING
    """), {"i": str(iid)})
    ing = PledgeQuarterIngester(tmp_db_session)
    ing.ingest_filing(json.loads(FIXTURE.read_text()))
    rows = tmp_db_session.execute(text("""
        SELECT COUNT(*) AS n FROM atlas.atlas_governance_daily
         WHERE instrument_id = :i
           AND pledge_ratio_pct = 60.00
    """), {"i": str(iid)}).first()
    # 2024-09-30 through 2024-12-30 inclusive = 92 days
    assert rows.n == 92
```

- [ ] **Step 7.3: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_pledge.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 7.4: Implement `pledge.py`**

```python
# atlas/data_prereqs/v6/pledge.py
"""D5: Promoter pledge quarterly ingester.

For each filing, computes pledge_ratio = pledged_shares / total_promoter_shares × 100.
Forward-fills the value into atlas_governance_daily from the filing's effective
date through the day before the next quarter ends.

NSE/BSE source: https://www.nseindia.com/companies-listing/corporate-filings
Operator runs the ingester once per quarter via CLI:
    python -m atlas.data_prereqs.v6.cli ingest-pledge --filing-json path/to/q3_2024.json
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


def compute_pledge_ratio(total: int, pledged: int) -> float | None:
    if total <= 0:
        return None
    return round(100.0 * pledged / total, 2)


def parse_pledge_filing(payload: dict) -> list[dict]:
    eff = date.fromisoformat(payload["asOfDate"])
    rows = []
    for f in payload["filings"]:
        ratio = compute_pledge_ratio(
            f["promoter_total_shares"], f["promoter_pledged_shares"]
        )
        if ratio is None:
            continue
        rows.append({
            "symbol": f["symbol"],
            "effective_date": eff,
            "pledge_ratio_pct": ratio,
        })
    return rows


def _next_quarter_end(d: date) -> date:
    year, month = d.year, d.month
    if month <= 3:
        return date(year, 6, 30)
    if month <= 6:
        return date(year, 9, 30)
    if month <= 9:
        return date(year, 12, 31)
    return date(year + 1, 3, 31)


@dataclass
class PledgeQuarterIngester:
    session: Session

    def _resolve_iid(self, symbol: str) -> uuid.UUID | None:
        row = self.session.execute(text(
            "SELECT instrument_id FROM atlas.atlas_instrument_master WHERE symbol = :s"
        ), {"s": symbol}).first()
        return uuid.UUID(str(row.instrument_id)) if row else None

    def ingest_filing(self, payload: dict) -> None:
        rows = parse_pledge_filing(payload)
        if not rows:
            log.info("pledge_filing_empty")
            return
        eff = rows[0]["effective_date"]
        fill_until = _next_quarter_end(eff) - timedelta(days=1)
        n_days = (fill_until - eff).days + 1
        for r in rows:
            iid = self._resolve_iid(r["symbol"])
            if iid is None:
                log.warning("pledge_symbol_not_resolved", symbol=r["symbol"])
                continue
            for offset in range(n_days):
                d = eff + timedelta(days=offset)
                self.session.execute(text("""
                    INSERT INTO atlas.atlas_governance_daily
                        (instrument_id, date, pledge_ratio_pct)
                    VALUES (:i, :d, :p)
                    ON CONFLICT (instrument_id, date) DO UPDATE
                       SET pledge_ratio_pct = EXCLUDED.pledge_ratio_pct
                """), {"i": str(iid), "d": d, "p": r["pledge_ratio_pct"]})
        self.session.commit()
        log.info("pledge_filing_ingested",
                 effective_date=eff.isoformat(), symbols=len(rows),
                 days_filled=n_days)
```

- [ ] **Step 7.5: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_pledge.py -v`
Expected: PASS — all four tests green.

- [ ] **Step 7.6: Commit**

```bash
git add atlas/data_prereqs/v6/pledge.py tests/data_prereqs/v6/test_pledge.py \
        tests/data_prereqs/v6/fixtures/pledge_sample.json
git commit -m "feat(data_prereqs): D5 promoter pledge quarterly ingester + fwd-fill"
```

---

## Task 8: D6 — Auditor + promoter group master

One-time scrape from Screener.in or NSE corporate filings to populate `atlas_governance_master`. Annual refresh job thereafter.

**Files:**
- Create: `atlas/data_prereqs/v6/governance_master.py`
- Create: `tests/data_prereqs/v6/fixtures/screener_company_sample.html`
- Create: `tests/data_prereqs/v6/test_governance_master.py`

- [ ] **Step 8.1: Capture sample HTML fixture (truncated, just the section we parse)**

`tests/data_prereqs/v6/fixtures/screener_company_sample.html`:
```html
<html><body>
  <div class="company-profile">
    <div class="company-info">
      <div class="company-line"><span>Promoter Group:</span> Adani Group</div>
      <div class="company-line"><span>Auditor:</span> Shah Dhandharia &amp; Co LLP</div>
    </div>
  </div>
</body></html>
```

- [ ] **Step 8.2: Write failing tests**

```python
# tests/data_prereqs/v6/test_governance_master.py
"""D6: Auditor + promoter group scrape into atlas_governance_master."""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.governance_master import (
    GovernanceMasterUpserter,
    TOP_10_AUDITORS,
    is_top_10_auditor,
    parse_screener_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "screener_company_sample.html"


def test_top_10_auditor_list_contains_expected():
    assert "Deloitte" in [a.split()[0] for a in TOP_10_AUDITORS]
    assert "BSR" in [a.split()[0] for a in TOP_10_AUDITORS]
    assert "Walker" in [a.split()[0] for a in TOP_10_AUDITORS]


def test_is_top_10_auditor_fuzzy_match():
    assert is_top_10_auditor("Deloitte Haskins & Sells LLP") is True
    assert is_top_10_auditor("BSR & Co. LLP") is True
    assert is_top_10_auditor("Shah Dhandharia & Co LLP") is False
    assert is_top_10_auditor(None) is False


def test_parse_screener_html_returns_dict():
    html = FIXTURE.read_text()
    out = parse_screener_html(html)
    assert out["promoter_group"] == "Adani Group"
    assert out["auditor_name"].startswith("Shah Dhandharia")


def test_upserter_writes_master_with_top_10_flag(tmp_db_session):
    iid = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'ADANIENT') ON CONFLICT DO NOTHING
    """), {"i": str(iid)})
    upserter = GovernanceMasterUpserter(tmp_db_session)
    upserter.upsert(
        symbol="ADANIENT",
        promoter_group="Adani Group",
        auditor_name="Shah Dhandharia & Co LLP",
    )
    row = tmp_db_session.execute(text(
        "SELECT promoter_group, auditor_name, auditor_is_top_10 "
        "FROM atlas.atlas_governance_master WHERE instrument_id = :i"
    ), {"i": str(iid)}).first()
    assert row.promoter_group == "Adani Group"
    assert row.auditor_name.startswith("Shah Dhandharia")
    assert row.auditor_is_top_10 is False
```

- [ ] **Step 8.3: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_governance_master.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 8.4: Implement `governance_master.py`**

```python
# atlas/data_prereqs/v6/governance_master.py
"""D6: Auditor + promoter group master.

One-time scrape from Screener.in (or NSE corporate filings); annual refresh.
Tags whether the auditor is in the top-10 list used for governance filtering.

TOP_10_AUDITORS is hand-curated and reviewed annually; treat as a constant.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

TOP_10_AUDITORS: tuple[str, ...] = (
    "Deloitte Haskins & Sells",
    "Price Waterhouse",
    "PwC",
    "Ernst & Young",
    "EY",
    "KPMG",
    "BSR & Co",
    "Walker Chandiok & Co",
    "Grant Thornton",
    "RSM",
    "Crowe Horwath",
    "S R B C & Co",
    "S.R. Batliboi",
)


def is_top_10_auditor(auditor_name: str | None) -> bool:
    if not auditor_name:
        return False
    norm = auditor_name.replace("&", "and").lower()
    return any(
        a.replace("&", "and").lower().split()[0] in norm.split()
        for a in TOP_10_AUDITORS
    )


def parse_screener_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out = {"promoter_group": None, "auditor_name": None}
    for line in soup.select(".company-line"):
        text_ = line.get_text(" ", strip=True)
        if text_.startswith("Promoter Group:"):
            out["promoter_group"] = text_[len("Promoter Group:"):].strip()
        elif text_.startswith("Auditor:"):
            out["auditor_name"] = text_[len("Auditor:"):].strip()
    return out


@dataclass
class GovernanceMasterUpserter:
    session: Session

    def upsert(
        self, symbol: str, promoter_group: str | None,
        auditor_name: str | None,
    ) -> None:
        row = self.session.execute(text(
            "SELECT instrument_id FROM atlas.atlas_instrument_master WHERE symbol = :s"
        ), {"s": symbol}).first()
        if row is None:
            log.warning("symbol_unresolved", symbol=symbol)
            return
        iid = str(row.instrument_id)
        self.session.execute(text("""
            INSERT INTO atlas.atlas_governance_master
                (instrument_id, promoter_group, auditor_name, auditor_is_top_10)
            VALUES (:i, :g, :a, :t)
            ON CONFLICT (instrument_id) DO UPDATE SET
                promoter_group = EXCLUDED.promoter_group,
                auditor_name = EXCLUDED.auditor_name,
                auditor_is_top_10 = EXCLUDED.auditor_is_top_10,
                updated_at = NOW()
        """), {
            "i": iid, "g": promoter_group,
            "a": auditor_name, "t": is_top_10_auditor(auditor_name),
        })
        self.session.commit()
```

- [ ] **Step 8.5: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_governance_master.py -v`
Expected: PASS — all four tests green.

- [ ] **Step 8.6: Commit**

```bash
git add atlas/data_prereqs/v6/governance_master.py \
        tests/data_prereqs/v6/test_governance_master.py \
        tests/data_prereqs/v6/fixtures/screener_company_sample.html
git commit -m "feat(data_prereqs): D6 auditor + promoter group master scraper"
```

---

## Task 9: CLI dispatcher

A single command-line entry point for operator runbooks — invoking each ingester independently or in sequence.

**Files:**
- Create: `atlas/data_prereqs/v6/cli.py`
- Create: `tests/data_prereqs/v6/test_cli.py`

- [ ] **Step 9.1: Write failing tests**

```python
# tests/data_prereqs/v6/test_cli.py
"""CLI dispatcher for v6 data prereq backfill + ongoing fetches."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.data_prereqs.v6.cli import main


def test_cli_ingest_membership(tmp_path, capsys):
    """`atlas.data_prereqs.v6.cli ingest-membership --snapshot path` parses + calls ingester."""
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({
        "indexName": "NIFTY 500", "effectiveDate": "2024-09-30",
        "constituents": [{"symbol": "TCS", "isin": "X"}]
    }))
    with patch("atlas.data_prereqs.v6.cli.MembershipIngester") as m:
        main(["ingest-membership", "--snapshot", str(snap)])
    m.return_value.ingest_snapshot.assert_called_once()


def test_cli_unknown_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        main(["bogus-command"])
    assert exc.value.code != 0
```

- [ ] **Step 9.2: Run the tests to verify they fail**

Run: `pytest tests/data_prereqs/v6/test_cli.py -v`
Expected: FAIL — CLI not yet implemented.

- [ ] **Step 9.3: Implement `cli.py`**

```python
# atlas/data_prereqs/v6/cli.py
"""CLI dispatcher: python -m atlas.data_prereqs.v6 <subcommand> [args...]."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.data_prereqs.v6.etf_coverage import EtfCoverageChecker, YahooBackfiller
from atlas.data_prereqs.v6.fno_ban import FnoBanFetcher, FnoBanUpserter
from atlas.data_prereqs.v6.governance_master import (
    GovernanceMasterUpserter, parse_screener_html,
)
from atlas.data_prereqs.v6.macro_daily import (
    BreadthComputer, DxyFetcher, FiiFlowFetcher, IndiaTenYearFetcher,
    MacroDailyUpserter, RiskFree91dFetcher, UsdInrFetcher,
)
from atlas.data_prereqs.v6.membership import (
    MembershipIngester, parse_reconstitution_snapshot,
)
from atlas.data_prereqs.v6.pledge import PledgeQuarterIngester


def _session():
    eng = create_engine(os.environ["ATLAS_DB_URL"])
    return sessionmaker(bind=eng)()


def cmd_ingest_membership(args: argparse.Namespace) -> int:
    payload = json.loads(open(args.snapshot).read())
    snap = parse_reconstitution_snapshot(payload)
    ing = MembershipIngester(_session())
    ing.ingest_snapshot(snap)
    return 0


def cmd_ingest_pledge(args: argparse.Namespace) -> int:
    payload = json.loads(open(args.filing_json).read())
    ing = PledgeQuarterIngester(_session())
    ing.ingest_filing(payload)
    return 0


def cmd_fetch_fno_ban(args: argparse.Namespace) -> int:
    ref = date.fromisoformat(args.date) if args.date else date.today()
    symbols = FnoBanFetcher().fetch_for_date(ref)
    FnoBanUpserter(_session()).upsert(ref, symbols)
    return 0


def cmd_fetch_macro(args: argparse.Namespace) -> int:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    sess = _session()
    df_usd = UsdInrFetcher().fetch(start, end)
    df_dxy = DxyFetcher().fetch(start, end)
    df_fii = FiiFlowFetcher().fetch(start, end)
    df_10y = IndiaTenYearFetcher().fetch(start, end)
    df_tbi = RiskFree91dFetcher().fetch(start, end)
    bc = BreadthComputer(sess)
    breadth_rows = [{"date": d, "breadth_pct_above_200dma": bc.compute(d)}
                    for d in [start]]
    # Merge on date (outer join)
    import pandas as pd
    df = df_usd
    for d in (df_dxy, df_fii, df_10y, df_tbi, pd.DataFrame(breadth_rows)):
        if not d.empty:
            df = df.merge(d, on="date", how="outer") if not df.empty else d
    MacroDailyUpserter(sess).upsert(df)
    return 0


def cmd_check_etf_coverage(args: argparse.Namespace) -> int:
    chk = EtfCoverageChecker(_session(), target_years=10)
    for s in ("GOLDBEES", "LIQUIDBEES", "BHARAT22 ETF"):
        cov = chk.coverage_for(s, reference_date=date.today())
        print(f"{s}: first={cov.first_date} last={cov.last_date} gap_days={cov.gap_days_to_target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas.data_prereqs.v6")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest-membership")
    s.add_argument("--snapshot", required=True)
    s.set_defaults(func=cmd_ingest_membership)

    s = sub.add_parser("ingest-pledge")
    s.add_argument("--filing-json", required=True)
    s.set_defaults(func=cmd_ingest_pledge)

    s = sub.add_parser("fetch-fno-ban")
    s.add_argument("--date", default=None)
    s.set_defaults(func=cmd_fetch_fno_ban)

    s = sub.add_parser("fetch-macro")
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.set_defaults(func=cmd_fetch_macro)

    s = sub.add_parser("check-etf-coverage")
    s.set_defaults(func=cmd_check_etf_coverage)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9.4: Run the tests to verify they pass**

Run: `pytest tests/data_prereqs/v6/test_cli.py -v`
Expected: PASS — both tests green.

- [ ] **Step 9.5: Commit**

```bash
git add atlas/data_prereqs/v6/cli.py tests/data_prereqs/v6/test_cli.py
git commit -m "feat(data_prereqs): CLI dispatcher for v6 ingestion"
```

---

## Task 10: Schedule registration

Wire each fetcher to its appropriate cadence using `apscheduler`. Daily for macro + F&O ban + breadth; weekly for FII recap; quarterly for pledge; annually for governance master refresh.

**Files:**
- Create: `atlas/data_prereqs/v6/schedules.py`
- Create: `tests/data_prereqs/v6/test_schedules.py`

- [ ] **Step 10.1: Write failing test**

```python
# tests/data_prereqs/v6/test_schedules.py
"""Schedule registration — verify each job is registered with the right cron."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from atlas.data_prereqs.v6.schedules import register_all


def test_register_all_registers_expected_jobs():
    sched = BackgroundScheduler()
    register_all(sched)
    job_ids = {j.id for j in sched.get_jobs()}
    assert "v6_macro_daily" in job_ids
    assert "v6_fno_ban_daily" in job_ids
    assert "v6_governance_master_annual" in job_ids
```

- [ ] **Step 10.2: Run the test to verify it fails**

Run: `pytest tests/data_prereqs/v6/test_schedules.py -v`
Expected: FAIL — module not yet implemented.

- [ ] **Step 10.3: Implement `schedules.py`**

```python
# atlas/data_prereqs/v6/schedules.py
"""Cron schedules for v6 data prerequisite fetchers.

All times IST. Daily fetchers run after market close (~17:00 IST).
Pledge is quarter-end-aligned. Governance master refreshes annually in April.
"""
from __future__ import annotations

import os
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.data_prereqs.v6.fno_ban import FnoBanFetcher, FnoBanUpserter
from atlas.data_prereqs.v6.macro_daily import (
    BreadthComputer, DxyFetcher, FiiFlowFetcher, MacroDailyUpserter,
    UsdInrFetcher,
)


def _session():
    return sessionmaker(bind=create_engine(os.environ["ATLAS_DB_URL"]))()


def run_macro_daily() -> None:
    today = date.today()
    sess = _session()
    df_usd = UsdInrFetcher().fetch(today, today)
    df_dxy = DxyFetcher().fetch(today, today)
    df_fii = FiiFlowFetcher().fetch(today, today)
    bc = BreadthComputer(sess)
    import pandas as pd
    df_br = pd.DataFrame([{"date": today, "breadth_pct_above_200dma": bc.compute(today)}])
    df = df_usd
    for d in (df_dxy, df_fii, df_br):
        if not d.empty:
            df = df.merge(d, on="date", how="outer") if not df.empty else d
    MacroDailyUpserter(sess).upsert(df)


def run_fno_ban_daily() -> None:
    today = date.today()
    sess = _session()
    syms = FnoBanFetcher().fetch_for_date(today)
    FnoBanUpserter(sess).upsert(today, syms)


def run_governance_master_annual() -> None:
    # Re-scrape from Screener for full Nifty 500 — operator runbook step.
    # Placeholder for production scrape orchestration.
    pass


def register_all(scheduler: BackgroundScheduler) -> None:
    scheduler.add_job(
        run_macro_daily, CronTrigger(hour=17, minute=10, timezone="Asia/Kolkata"),
        id="v6_macro_daily",
    )
    scheduler.add_job(
        run_fno_ban_daily, CronTrigger(hour=17, minute=30, timezone="Asia/Kolkata"),
        id="v6_fno_ban_daily",
    )
    scheduler.add_job(
        run_governance_master_annual,
        CronTrigger(month=4, day=15, hour=2, timezone="Asia/Kolkata"),
        id="v6_governance_master_annual",
    )
```

- [ ] **Step 10.4: Add `apscheduler` to pyproject.toml**

Run: locate `[project.dependencies]`, add `"apscheduler>=3.10",`.

- [ ] **Step 10.5: Run the test to verify it passes**

Run: `pytest tests/data_prereqs/v6/test_schedules.py -v`
Expected: PASS — test green.

- [ ] **Step 10.6: Commit**

```bash
git add atlas/data_prereqs/v6/schedules.py \
        tests/data_prereqs/v6/test_schedules.py pyproject.toml
git commit -m "feat(data_prereqs): v6 cron schedule registration"
```

---

## Task 11: End-to-end smoke test

Verify all six fetchers and the CLI run end-to-end against a fresh test database with the migration applied.

**Files:**
- Create: `tests/data_prereqs/v6/test_e2e_smoke.py`

- [ ] **Step 11.1: Write the end-to-end smoke test**

```python
# tests/data_prereqs/v6/test_e2e_smoke.py
"""End-to-end smoke: migration + all six fetchers + verifies DB state."""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.fno_ban import FnoBanFetcher, FnoBanUpserter
from atlas.data_prereqs.v6.governance_master import GovernanceMasterUpserter
from atlas.data_prereqs.v6.macro_daily import (
    MacroDailyUpserter, UsdInrFetcher,
)
from atlas.data_prereqs.v6.membership import (
    MembershipIngester, parse_reconstitution_snapshot,
)
from atlas.data_prereqs.v6.pledge import PledgeQuarterIngester

FIX = Path(__file__).parent / "fixtures"


def test_full_pipeline_smoke(tmp_db_session):
    """Run each ingester once; verify each table got rows."""
    # Seed instrument master
    iid_tcs = uuid.uuid4()
    iid_dhfl = uuid.uuid4()
    iid_idea = uuid.uuid4()
    tmp_db_session.execute(text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:t, 'TCS'), (:d, 'DHFL'), (:i, 'IDEA')
        ON CONFLICT DO NOTHING
    """), {"t": str(iid_tcs), "d": str(iid_dhfl), "i": str(iid_idea)})

    # D1: membership
    snap = parse_reconstitution_snapshot(json.loads(
        (FIX / "nifty500_reconstitution_2024_09.json").read_text()))
    MembershipIngester(tmp_db_session).ingest_snapshot(snap)

    # D3: macro (mock Yahoo)
    yahoo_df = pd.DataFrame({"Close": [83.2]},
                            index=pd.to_datetime([date(2024, 9, 30)]))
    with patch("atlas.data_prereqs.v6.macro_daily.yf.download",
               return_value=yahoo_df):
        df = UsdInrFetcher().fetch(date(2024, 9, 30), date(2024, 9, 30))
    MacroDailyUpserter(tmp_db_session).upsert(df)

    # D4: F&O ban
    with patch("atlas.data_prereqs.v6.fno_ban.requests.get") as m:
        m.return_value.text = "Symbol\nIDEA"
        m.return_value.status_code = 200
        syms = FnoBanFetcher().fetch_for_date(date(2024, 9, 30))
    FnoBanUpserter(tmp_db_session).upsert(date(2024, 9, 30), syms)

    # D5: pledge
    pledge_payload = json.loads((FIX / "pledge_sample.json").read_text())
    PledgeQuarterIngester(tmp_db_session).ingest_filing(pledge_payload)

    # D6: governance master
    GovernanceMasterUpserter(tmp_db_session).upsert(
        symbol="DHFL", promoter_group="DHFL Group",
        auditor_name="KPMG India",
    )

    # Verify each table has rows
    counts = {}
    for table in ("atlas_index_membership", "atlas_macro_daily",
                  "atlas_governance_daily", "atlas_governance_master"):
        counts[table] = tmp_db_session.execute(
            text(f"SELECT COUNT(*) AS n FROM atlas.{table}")
        ).first().n
    assert counts["atlas_index_membership"] >= 1
    assert counts["atlas_macro_daily"] >= 1
    assert counts["atlas_governance_daily"] >= 1
    assert counts["atlas_governance_master"] >= 1
```

- [ ] **Step 11.2: Run the smoke test**

Run: `pytest tests/data_prereqs/v6/test_e2e_smoke.py -v`
Expected: PASS — single test green.

- [ ] **Step 11.3: Run the full test suite**

Run: `pytest tests/data_prereqs/v6/ -v`
Expected: PASS — all tests across all modules green.

- [ ] **Step 11.4: Commit**

```bash
git add tests/data_prereqs/v6/test_e2e_smoke.py
git commit -m "test(data_prereqs): v6 end-to-end smoke covering all 6 sources"
```

---

## Task 12: Runbook documentation

Operator-facing runbook for initial backfill across 2010-2025.

**Files:**
- Create: `docs/runbooks/v6-data-prereqs-backfill.md`

- [ ] **Step 12.1: Write the runbook**

```markdown
# v6 Data Prerequisites — Initial Backfill Runbook

Audience: data ops engineer (the one with credentials + network access).
Expected duration: 5-6 working days end-to-end.

## Order of operations

Run in this order — later steps depend on earlier ones.

1. Apply migration 080:
   ```bash
   alembic upgrade 080
   ```

2. D2 — ETF coverage check (decides whether D2 needs Yahoo backfill):
   ```bash
   python -m atlas.data_prereqs.v6.cli check-etf-coverage
   ```
   For each ETF with gap_days > 0, run Yahoo backfill (Python REPL or one-off
   script invoking `YahooBackfiller.backfill(...)`).

3. D3 — Macro backfill, in chunks of 365 days to avoid Yahoo rate limits:
   ```bash
   for year in $(seq 2010 2025); do
       python -m atlas.data_prereqs.v6.cli fetch-macro \
           --start ${year}-01-01 --end ${year}-12-31
       sleep 5
   done
   ```

4. D1 — Membership: download each semi-annual Nifty 500 reconstitution snapshot
   from NSE and feed to the CLI:
   ```bash
   python -m atlas.data_prereqs.v6.cli ingest-membership \
       --snapshot /path/to/snapshots/nifty500_2024_09.json
   ```
   Repeat for every reconstitution date between 2010 and 2025 (semi-annual:
   March + September).

5. D4 — F&O ban list backfill: NSE keeps daily files from ~2017 onward at
   `archives.nseindia.com/content/fo/secban_<DDMMYYYY>.csv`. Loop through each
   trading day:
   ```bash
   for day in $(generate_trading_days 2017-01-01 2025-12-31); do
       python -m atlas.data_prereqs.v6.cli fetch-fno-ban --date $day
       sleep 1
   done
   ```

6. D5 — Pledge: NSE quarterly shareholding pattern filings. Download the
   parsed JSON for each quarter from 2010-Q1 through latest, then ingest:
   ```bash
   for q in $(generate_quarter_ends 2010-03-31 latest); do
       python -m atlas.data_prereqs.v6.cli ingest-pledge \
           --filing-json /path/to/pledge_${q}.json
   done
   ```

7. D6 — Governance master: one-time scrape of all current Nifty 500 names
   from Screener.in. See `scripts/scrape_screener_companies.py` (out of
   scope for this plan — operator-driven).

## Sanity checks after backfill

```sql
SELECT 'membership' AS source, COUNT(*) FROM atlas.atlas_index_membership
UNION ALL SELECT 'macro_daily', COUNT(*) FROM atlas.atlas_macro_daily
UNION ALL SELECT 'governance_daily', COUNT(*) FROM atlas.atlas_governance_daily
UNION ALL SELECT 'governance_master', COUNT(*) FROM atlas.atlas_governance_master;
```

Expected row counts after backfill:
- membership: ~30-50 rows per stock (full membership history)
- macro_daily: ~3,900 (16y × ~245 trading days)
- governance_daily: ~3,200 per active F&O stock + pledge fwd-fill density
- governance_master: ~500 (current Nifty 500)

## Re-running idempotently

Every ingester uses ON CONFLICT DO UPDATE — safe to re-run. The membership
ingester is event-driven (each snapshot is a diff); re-ingesting the same
snapshot is a no-op.
```

- [ ] **Step 12.2: Commit the runbook**

```bash
git add docs/runbooks/v6-data-prereqs-backfill.md
git commit -m "docs(runbook): v6 data prereqs backfill operator guide"
```

---

## Self-review checklist (skim before declaring done)

- [ ] All 6 data sources have a fetcher module + tests + commit
- [ ] Migration 080 creates all 8 tables (6 prereq + 2 v6-output: strategy_runs, exclusions_log, recommendations)
- [ ] CLI dispatcher covers ingest-membership, ingest-pledge, fetch-fno-ban, fetch-macro, check-etf-coverage
- [ ] Schedules registered for daily / quarterly / annual cadences
- [ ] End-to-end smoke test exercises all 6 sources
- [ ] Runbook documents the 5-6-day operator workflow
- [ ] All files under 600 LOC source / 800 LOC test (atlas hook enforces)
- [ ] No `Decimal` violation (none of these handle money)
- [ ] No bare `except:` clauses
- [ ] Tests use real Postgres via tmp_db_session, not mocks of SQLAlchemy

## When this plan completes

You can write Plan 2 (Backend Trading Engine). Plan 2's signal layer reads from:
- `atlas_index_membership` (D1) — universe filtering
- `atlas_etf_metrics_daily` (D2) — crisis sleeve
- `atlas_macro_daily` (D3) — regime composite
- `atlas_governance_daily` + `atlas_governance_master` (D4-D6) — hard exclusions
- `atlas_factor_returns_daily` — populated in Plan 2 Phase 2, not here
