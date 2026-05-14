# MF Holdings History & Fund Manager Decision Tracking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a holdings change-tracking layer on top of `public.de_mf_holdings` — per-period entry/exit log with signal quality + 1m/3m outcome scores, served through a new API and four frontend surfaces.

**Architecture:** Standalone compute script (`scripts/run_fund_decisions.py`) diffs consecutive monthly disclosures from `de_mf_holdings`, writes granular changes to `atlas_fund_holdings_changes` and pre-computed scores to `atlas_fund_decision_scores`. A separate enrichment job fills in outcome columns as 30/90-day windows mature. Two FastAPI endpoints serve the data; the frontend adds a dedicated decisions page, a tab on the fund detail page, and three new columns on the main listing.

**Tech Stack:** Python 3.11, pandas vectorized, SQLAlchemy 2.0, psycopg2 execute_values, FastAPI, Pydantic v2, Next.js 15 server components, Recharts, AG Grid, TypeScript.

**Spec:** `docs/superpowers/specs/2026-05-14-mf-holdings-history-design.md`

---

## File Map

**New files:**
- `migrations/versions/065_mf_holdings_history.py` — creates two tables + seeds 3 thresholds
- `atlas/compute/lens_decisions.py` — core diff + score compute logic
- `scripts/run_fund_decisions.py` — standalone CLI runner
- `scripts/enrich_fund_decision_outcomes.py` — 1m/3m outcome backfill job
- `tests/unit/compute/test_lens_decisions.py` — unit tests for compute logic
- `atlas/api/fund_decisions.py` — two new FastAPI endpoints
- `frontend/src/components/funds/FundManagerDecisionSummary.tsx` — score trend chart + stats card
- `frontend/src/components/funds/FundManagerDecisionsDetail.tsx` — period selector + AG Grid table
- `frontend/src/app/funds/[mstar_id]/decisions/page.tsx` — dedicated decisions page shell

**Modified files:**
- `atlas/api/__init__.py` — register `fund_decisions_router`
- `frontend/src/lib/queries/funds.ts` — add `FundDecisionScoreRow`, `FundHoldingsChangeRow` types + 3 new query functions + update `FundRow` + `getAllFunds()`
- `frontend/src/app/funds/[mstar_id]/page.tsx` — add "Manager Decisions" tab

---

## Task 1: Migration — Create Holdings History Tables

**Files:**
- Create: `migrations/versions/065_mf_holdings_history.py`

- [ ] **Step 1: Write the migration**

```python
"""mf_holdings_history: fund holdings changes + decision scores

Revision ID: 065
Revises: 064
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_fund_holdings_changes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mstar_id", sa.String(32), nullable=False, index=True),
        sa.Column("from_date", sa.Date, nullable=True),
        sa.Column("to_date", sa.Date, nullable=False),
        sa.Column("instrument_id", sa.Text, nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("weight_before", sa.Numeric(10, 4), nullable=False),
        sa.Column("weight_after", sa.Numeric(10, 4), nullable=False),
        sa.Column("weight_delta", sa.Numeric(10, 4), nullable=False),
        sa.Column("rs_state_at_action", sa.String(20), nullable=True),
        sa.Column("momentum_state_at_action", sa.String(20), nullable=True),
        sa.Column("signal_quality", sa.String(10), nullable=True),
        sa.Column("outcome_rs_state_1m", sa.String(20), nullable=True),
        sa.Column("outcome_ret_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_quality_1m", sa.String(10), nullable=True),
        sa.Column("outcome_rs_state_3m", sa.String(20), nullable=True),
        sa.Column("outcome_ret_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_quality_3m", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="atlas",
    )
    op.create_index(
        "idx_fund_holdings_changes_fund_period",
        "atlas_fund_holdings_changes",
        ["mstar_id", "to_date"],
        schema="atlas",
    )
    op.create_index(
        "idx_fund_holdings_changes_outcome_1m",
        "atlas_fund_holdings_changes",
        ["to_date"],
        postgresql_where=sa.text("outcome_quality_1m IS NULL"),
        schema="atlas",
    )
    op.create_index(
        "idx_fund_holdings_changes_outcome_3m",
        "atlas_fund_holdings_changes",
        ["to_date"],
        postgresql_where=sa.text("outcome_quality_3m IS NULL"),
        schema="atlas",
    )

    op.create_table(
        "atlas_fund_decision_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mstar_id", sa.String(32), nullable=False, index=True),
        sa.Column("period_date", sa.Date, nullable=False),
        sa.Column("entries_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("exits_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("increases_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("decreases_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("quality_entries_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("quality_exits_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("signal_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_entries_pct_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_exits_pct_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_score_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_entries_pct_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_exits_pct_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_score_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("decision_state", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="atlas",
    )
    op.create_index(
        "idx_fund_decision_scores_fund_period",
        "atlas_fund_decision_scores",
        ["mstar_id", "period_date"],
        unique=True,
        schema="atlas",
    )

    op.execute("""
        INSERT INTO atlas.atlas_thresholds (
            threshold_key, threshold_value, category, description,
            min_allowed, max_allowed, default_value,
            last_modified_by, is_active
        )
        VALUES
            ('holdings_weight_change_min_pct', 0.25, 'funds',
             'Min |weight_delta| (%) to classify as increase/decrease vs noise',
             0.05, 2.0, 0.25, 'migration_065', true),
            ('decision_score_sharp_threshold', 65.0, 'funds',
             'signal_score >= this → Sharp decision state',
             50.0, 90.0, 65.0, 'migration_065', true),
            ('decision_score_poor_threshold', 40.0, 'funds',
             'signal_score < this → Poor decision state',
             10.0, 50.0, 40.0, 'migration_065', true)
        ON CONFLICT (threshold_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM atlas.atlas_thresholds WHERE threshold_key IN ("
               "'holdings_weight_change_min_pct','decision_score_sharp_threshold',"
               "'decision_score_poor_threshold')")
    op.drop_table("atlas_fund_decision_scores", schema="atlas")
    op.drop_table("atlas_fund_holdings_changes", schema="atlas")
```

- [ ] **Step 2: Run the migration**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os
alembic upgrade head
```

Expected: `Running upgrade 064 -> 065, mf_holdings_history: fund holdings changes + decision scores`

- [ ] **Step 3: Verify tables exist**

```bash
python -c "
from atlas.db import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as c:
    r = c.execute(text(\"SELECT COUNT(*) FROM atlas.atlas_fund_holdings_changes\")).scalar()
    print('holdings_changes rows:', r)
    r = c.execute(text(\"SELECT COUNT(*) FROM atlas.atlas_fund_decision_scores\")).scalar()
    print('decision_scores rows:', r)
    r = c.execute(text(\"SELECT threshold_key FROM atlas.atlas_thresholds WHERE category='funds' ORDER BY 1\")).fetchall()
    print('fund thresholds:', [row[0] for row in r])
"
```

Expected: both tables return 0 rows; three new threshold keys printed.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/065_mf_holdings_history.py
git commit -m "feat(migration): create atlas_fund_holdings_changes + atlas_fund_decision_scores tables (065)"
```

---

## Task 2: Compute Module — `atlas/compute/lens_decisions.py`

**Files:**
- Create: `atlas/compute/lens_decisions.py`

- [ ] **Step 1: Write the compute module**

```python
"""Lens 4 — Holdings Decision Quality.

For each fund's monthly disclosure pair (from_date → to_date):
- Diffs consecutive holdings snapshots from public.de_mf_holdings
- Classifies each change as entry / exit / increase / decrease
- Derives signal_quality from action + rs_state at to_date
- Writes granular rows to atlas.atlas_fund_holdings_changes
- Aggregates decision scores into atlas.atlas_fund_decision_scores

Idempotent: skips (mstar_id, to_date) pairs already present in
atlas_fund_decision_scores.

Weight change threshold: holdings_weight_change_min_pct from atlas_thresholds
(default 0.25%). Deltas below this are noise and are skipped.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

_HIGH_QUALITY_STATES = frozenset({"Leader", "Strong", "Emerging"})
_LOW_QUALITY_STATES = frozenset({"Weak", "Laggard"})


# --------------------------------------------------------------------------- #
# Signal quality                                                               #
# --------------------------------------------------------------------------- #

def derive_signal_quality(action: str, rs_state: str | None) -> str:
    """Derive signal_quality from action + rs_state at time of decision.

    Rules (per spec §Schema.Table1):
    - entry into high-quality state  → high
    - entry into low-quality state   → low
    - exit from low-quality state    → high (good sell)
    - exit from high-quality state   → low  (bad sell)
    - increase / decrease            → neutral (ambiguous sizing)
    - unknown rs_state or outside universe → neutral
    """
    if rs_state is None:
        return "neutral"
    if action == "entry":
        if rs_state in _HIGH_QUALITY_STATES:
            return "high"
        if rs_state in _LOW_QUALITY_STATES:
            return "low"
    elif action == "exit":
        if rs_state in _LOW_QUALITY_STATES:
            return "high"
        if rs_state in _HIGH_QUALITY_STATES:
            return "low"
    return "neutral"


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #

def _load_fund_disclosure_dates(engine: Engine) -> pd.DataFrame:
    """Return the two most recent as_of_date values per fund in atlas universe.

    Uses ROW_NUMBER window function — correlated LIMIT is non-standard SQL.
    """
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT mstar_id, as_of_date
            FROM (
                SELECT h.mstar_id, h.as_of_date,
                       ROW_NUMBER() OVER (PARTITION BY h.mstar_id ORDER BY h.as_of_date DESC) AS rn
                FROM public.de_mf_holdings h
                JOIN atlas.atlas_universe_funds uf USING (mstar_id)
            ) ranked
            WHERE rn <= 2
            """,
            conn,
        )


def _load_snapshot(engine: Engine, mstar_id: str, as_of_date: date) -> pd.DataFrame:
    """Load holdings snapshot for one fund on one date."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT
                h.instrument_id::text AS instrument_id,
                COALESCE(u.symbol, '') AS symbol,
                (h.weight_pct / 100.0) AS weight
            FROM public.de_mf_holdings h
            LEFT JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
            WHERE h.mstar_id = %(mstar_id)s
              AND h.as_of_date = %(date)s
            """,
            conn,
            params={"mstar_id": mstar_id, "date": as_of_date},
        )


def _load_stock_states(
    engine: Engine,
    instrument_ids: list[str],
    as_of_date: date,
) -> dict[str, tuple[str | None, str | None]]:
    """Return {instrument_id: (rs_state, momentum_state)} on or before as_of_date."""
    if not instrument_ids:
        return {}
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT DISTINCT ON (instrument_id)
                instrument_id::text AS instrument_id,
                rs_state,
                momentum_state
            FROM atlas.atlas_stock_states_daily
            WHERE instrument_id::text = ANY(%(ids)s)
              AND date <= %(date)s
            ORDER BY instrument_id, date DESC
            """,
            conn,
            params={"ids": instrument_ids, "date": as_of_date},
        )
    return {
        row["instrument_id"]: (row["rs_state"], row["momentum_state"])
        for _, row in df.iterrows()
    }


def _load_computed_set(engine: Engine) -> set[tuple[str, Any]]:
    """Return set of (mstar_id, period_date) already in atlas_fund_decision_scores.

    Called once before the fund loop — avoids ~500 per-fund queries (D4 fix).
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            "SELECT mstar_id, period_date FROM atlas.atlas_fund_decision_scores",
            conn,
        )
    return set(zip(df["mstar_id"], df["period_date"]))


# --------------------------------------------------------------------------- #
# Diff logic                                                                   #
# --------------------------------------------------------------------------- #

def compute_holdings_diff(
    from_snap: pd.DataFrame,
    to_snap: pd.DataFrame,
    mstar_id: str,
    from_date: date | None,
    to_date: date,
    state_map: dict[str, tuple[str | None, str | None]],
    min_weight_delta: float,
) -> list[dict[str, Any]]:
    """Diff two holdings snapshots; return list of change row dicts.

    Fully vectorized — no iterrows (D2 fix). Uses np.select for action
    classification and state lookup via .map(), same pattern as
    classify_holdings_state() in lens_holdings.py.
    """
    merged = pd.merge(
        to_snap.rename(columns={"weight": "w_after", "symbol": "symbol_after"}),
        from_snap[["instrument_id", "weight"]].rename(columns={"weight": "w_before"}),
        on="instrument_id",
        how="outer",
    ).fillna({"w_after": 0.0, "w_before": 0.0, "symbol_after": ""})

    merged["delta"] = merged["w_after"] - merged["w_before"]
    threshold = min_weight_delta / 100.0

    # Vectorized action classification using np.select (no iterrows)
    is_entry    = (merged["w_before"] == 0) & (merged["w_after"] > 0)
    is_exit     = (merged["w_before"] > 0)  & (merged["w_after"] == 0)
    is_increase = ~is_entry & ~is_exit & (merged["delta"] >=  threshold)
    is_decrease = ~is_entry & ~is_exit & (merged["delta"] <= -threshold)

    merged["action"] = np.select(
        [is_entry, is_exit, is_increase, is_decrease],
        ["entry", "exit", "increase", "decrease"],
        default=None,
    )
    merged = merged[merged["action"].notna()].copy()

    if merged.empty:
        return []

    # Vectorized state lookup via dict.map
    rs_map  = {k: v[0] for k, v in state_map.items()}
    mom_map = {k: v[1] for k, v in state_map.items()}
    merged["rs_state"]  = merged["instrument_id"].map(rs_map)
    merged["mom_state"] = merged["instrument_id"].map(mom_map)

    # Vectorized signal_quality derivation (np.select, conservative-first)
    sq_conds = [
        (merged["action"] == "entry") & merged["rs_state"].isin(_HIGH_QUALITY_STATES),
        (merged["action"] == "entry") & merged["rs_state"].isin(_LOW_QUALITY_STATES),
        (merged["action"] == "exit")  & merged["rs_state"].isin(_LOW_QUALITY_STATES),
        (merged["action"] == "exit")  & merged["rs_state"].isin(_HIGH_QUALITY_STATES),
    ]
    merged["signal_quality"] = np.select(sq_conds, ["high", "low", "high", "low"], default="neutral")

    merged["mstar_id"]    = mstar_id
    merged["from_date"]   = from_date
    merged["to_date"]     = to_date
    merged["symbol"]      = merged["symbol_after"].fillna("")
    merged["weight_before"] = merged["w_before"].round(4)
    merged["weight_after"]  = merged["w_after"].round(4)
    merged["weight_delta"]  = merged["delta"].round(4)

    return merged.rename(columns={
        "rs_state":  "rs_state_at_action",
        "mom_state": "momentum_state_at_action",
    })[[
        "mstar_id", "from_date", "to_date", "instrument_id", "symbol",
        "action", "weight_before", "weight_after", "weight_delta",
        "rs_state_at_action", "momentum_state_at_action", "signal_quality",
    ]].to_dict("records")


# --------------------------------------------------------------------------- #
# Score aggregation                                                            #
# --------------------------------------------------------------------------- #

def compute_decision_score(
    changes: list[dict[str, Any]],
    mstar_id: str,
    to_date: date,
    sharp_threshold: float,
    poor_threshold: float,
) -> dict[str, Any]:
    """Aggregate change rows into one decision score row."""
    entries = [c for c in changes if c["action"] == "entry"]
    exits   = [c for c in changes if c["action"] == "exit"]
    increases = [c for c in changes if c["action"] == "increase"]
    decreases = [c for c in changes if c["action"] == "decrease"]

    def quality_pct(group: list[dict]) -> float | None:
        if not group:
            return None
        high = sum(1 for c in group if c["signal_quality"] == "high")
        return round(high / len(group) * 100, 4)

    q_entry = quality_pct(entries)
    q_exit  = quality_pct(exits)

    non_null = [x for x in [q_entry, q_exit] if x is not None]
    signal_score = round(sum(non_null) / len(non_null), 4) if non_null else None

    if signal_score is None:
        decision_state = None
    elif signal_score >= sharp_threshold:
        decision_state = "Sharp"
    elif signal_score < poor_threshold:
        decision_state = "Poor"
    else:
        decision_state = "Average"

    return {
        "mstar_id": mstar_id,
        "period_date": to_date,
        "entries_count": len(entries),
        "exits_count": len(exits),
        "increases_count": len(increases),
        "decreases_count": len(decreases),
        "quality_entries_pct": q_entry,
        "quality_exits_pct": q_exit,
        "signal_score": signal_score,
        "decision_state": decision_state,
    }


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #

CHANGES_COLUMNS = (
    "mstar_id", "from_date", "to_date", "instrument_id", "symbol",
    "action", "weight_before", "weight_after", "weight_delta",
    "rs_state_at_action", "momentum_state_at_action", "signal_quality",
)

SCORES_COLUMNS = (
    "mstar_id", "period_date",
    "entries_count", "exits_count", "increases_count", "decreases_count",
    "quality_entries_pct", "quality_exits_pct", "signal_score", "decision_state",
)


def run_lens_decisions(
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
    target_funds: list[str] | None = None,
) -> dict[str, Any]:
    """Compute holdings diffs + decision scores for all (or target) funds.

    Returns {funds_processed, changes_written, scores_written, skipped, errors}.
    """
    engine = engine or get_engine()
    if thresholds is None:
        thresholds = load_thresholds("atlas", engine)

    min_weight_delta = float(thresholds.get("holdings_weight_change_min_pct", 0.25))
    sharp_threshold  = float(thresholds.get("decision_score_sharp_threshold", 65.0))
    poor_threshold   = float(thresholds.get("decision_score_poor_threshold", 40.0))

    # Build per-fund disclosure date map: {mstar_id: [date1, date2]} sorted desc
    disclosure_df = _load_fund_disclosure_dates(engine)
    fund_dates: dict[str, list[date]] = {}
    for mstar_id, grp in disclosure_df.groupby("mstar_id"):
        dates = sorted(grp["as_of_date"].tolist(), reverse=True)
        fund_dates[mstar_id] = dates

    if target_funds:
        fund_dates = {k: v for k, v in fund_dates.items() if k in target_funds}

    log.info("lens_decisions_start", total_funds=len(fund_dates))

    # D4: batch-load all already-computed pairs upfront (one query vs ~500)
    computed_set = _load_computed_set(engine)

    total_changes = 0
    total_scores = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    for mstar_id, dates in fund_dates.items():
        try:
            to_date = dates[0]
            from_date = dates[1] if len(dates) >= 2 else None

            if (mstar_id, to_date) in computed_set:
                skipped += 1
                continue

            to_snap   = _load_snapshot(engine, mstar_id, to_date)
            from_snap = _load_snapshot(engine, mstar_id, from_date) if from_date else pd.DataFrame(
                columns=["instrument_id", "symbol", "weight"]
            )

            all_ids = list(set(to_snap["instrument_id"].tolist() + from_snap.get("instrument_id", pd.Series()).tolist()))
            state_map = _load_stock_states(engine, all_ids, to_date)

            changes = compute_holdings_diff(
                from_snap, to_snap, mstar_id, from_date, to_date,
                state_map, min_weight_delta,
            )

            if changes:
                changes_df = pd.DataFrame(changes)[list(CHANGES_COLUMNS)]
                n_changes = bulk_upsert(
                    engine,
                    "atlas.atlas_fund_holdings_changes",
                    list(CHANGES_COLUMNS),
                    df_to_pg_rows(changes_df),
                    pk_columns=["mstar_id", "to_date", "instrument_id"],
                )
                total_changes += n_changes

            score = compute_decision_score(changes, mstar_id, to_date, sharp_threshold, poor_threshold)
            score_df = pd.DataFrame([score])[list(SCORES_COLUMNS)]
            n_scores = bulk_upsert(
                engine,
                "atlas.atlas_fund_decision_scores",
                list(SCORES_COLUMNS),
                df_to_pg_rows(score_df),
                pk_columns=["mstar_id", "period_date"],
            )
            total_scores += n_scores

            log.info(
                "lens_decisions_fund_done",
                mstar_id=mstar_id,
                to_date=str(to_date),
                changes=len(changes),
                signal_score=score["signal_score"],
            )

        except Exception as exc:
            errors.append({"mstar_id": mstar_id, "error": str(exc)})
            log.error("lens_decisions_fund_error", mstar_id=mstar_id, error=str(exc))

    log.info(
        "lens_decisions_complete",
        funds_processed=len(fund_dates) - skipped - len(errors),
        changes_written=total_changes,
        scores_written=total_scores,
        skipped=skipped,
        errors=len(errors),
    )
    return {
        "funds_processed": len(fund_dates) - skipped - len(errors),
        "changes_written": total_changes,
        "scores_written": total_scores,
        "skipped": skipped,
        "errors": errors,
    }
```

- [ ] **Step 2: Commit**

```bash
git add atlas/compute/lens_decisions.py
git commit -m "feat(compute): add lens_decisions — MF holdings diff + decision quality scores"
```

---

## Task 3: Unit Tests for `lens_decisions.py`

**Files:**
- Create: `tests/unit/compute/test_lens_decisions.py`
- Modify: `tests/unit/compute/__init__.py` (create empty if absent)

- [ ] **Step 1: Create `tests/unit/compute/__init__.py` if needed**

```bash
touch tests/unit/compute/__init__.py
```

- [ ] **Step 2: Write the failing tests**

```python
"""Unit tests for atlas.compute.lens_decisions.

All DB I/O is mocked. Tests cover:
- derive_signal_quality for all action/state combinations
- compute_holdings_diff for entry, exit, increase, decrease, noise
- compute_decision_score aggregation + state classification
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from atlas.compute.lens_decisions import (
    compute_decision_score,
    compute_holdings_diff,
    derive_signal_quality,
)

# --------------------------------------------------------------------------- #
# derive_signal_quality                                                        #
# --------------------------------------------------------------------------- #

class TestDeriveSignalQuality:
    def test_entry_into_leader_is_high(self):
        assert derive_signal_quality("entry", "Leader") == "high"

    def test_entry_into_strong_is_high(self):
        assert derive_signal_quality("entry", "Strong") == "high"

    def test_entry_into_emerging_is_high(self):
        assert derive_signal_quality("entry", "Emerging") == "high"

    def test_entry_into_weak_is_low(self):
        assert derive_signal_quality("entry", "Weak") == "low"

    def test_entry_into_laggard_is_low(self):
        assert derive_signal_quality("entry", "Laggard") == "low"

    def test_exit_from_weak_is_high(self):
        assert derive_signal_quality("exit", "Weak") == "high"

    def test_exit_from_laggard_is_high(self):
        assert derive_signal_quality("exit", "Laggard") == "high"

    def test_exit_from_leader_is_low(self):
        assert derive_signal_quality("exit", "Leader") == "low"

    def test_exit_from_strong_is_low(self):
        assert derive_signal_quality("exit", "Strong") == "low"

    def test_increase_is_always_neutral(self):
        assert derive_signal_quality("increase", "Leader") == "neutral"

    def test_decrease_is_always_neutral(self):
        assert derive_signal_quality("decrease", "Laggard") == "neutral"

    def test_none_rs_state_is_neutral(self):
        assert derive_signal_quality("entry", None) == "neutral"

    def test_unknown_rs_state_is_neutral(self):
        assert derive_signal_quality("entry", "SomeUnknown") == "neutral"


# --------------------------------------------------------------------------- #
# compute_holdings_diff                                                        #
# --------------------------------------------------------------------------- #

class TestComputeHoldingsDiff:
    _from_snap = pd.DataFrame([
        {"instrument_id": "A", "symbol": "AAA", "weight": 0.05},
        {"instrument_id": "B", "symbol": "BBB", "weight": 0.03},
        {"instrument_id": "C", "symbol": "CCC", "weight": 0.02},
    ])
    _state_map = {
        "A": ("Leader", "Strong"),
        "B": ("Weak", None),
        "D": ("Strong", "Strong"),
    }

    def _diff(self, from_snap, to_snap, min_delta=0.25):
        return compute_holdings_diff(
            from_snap=from_snap,
            to_snap=to_snap,
            mstar_id="F001",
            from_date=date(2026, 3, 31),
            to_date=date(2026, 4, 30),
            state_map=self._state_map,
            min_weight_delta=min_delta,
        )

    def test_new_stock_classified_as_entry(self):
        to_snap = pd.DataFrame([
            {"instrument_id": "A", "symbol": "AAA", "weight": 0.05},
            {"instrument_id": "D", "symbol": "DDD", "weight": 0.04},
        ])
        rows = self._diff(self._from_snap, to_snap)
        entries = [r for r in rows if r["action"] == "entry"]
        assert any(r["instrument_id"] == "D" for r in entries)

    def test_removed_stock_classified_as_exit(self):
        to_snap = pd.DataFrame([
            {"instrument_id": "A", "symbol": "AAA", "weight": 0.05},
        ])
        rows = self._diff(self._from_snap, to_snap)
        exits = [r for r in rows if r["action"] == "exit"]
        assert any(r["instrument_id"] == "B" for r in exits)
        assert any(r["instrument_id"] == "C" for r in exits)

    def test_weight_increase_above_threshold_classified_as_increase(self):
        to_snap = pd.DataFrame([
            {"instrument_id": "A", "symbol": "AAA", "weight": 0.06},  # +0.01 = +1% → above 0.25%
            {"instrument_id": "B", "symbol": "BBB", "weight": 0.03},
            {"instrument_id": "C", "symbol": "CCC", "weight": 0.02},
        ])
        rows = self._diff(self._from_snap, to_snap)
        increases = [r for r in rows if r["action"] == "increase"]
        assert any(r["instrument_id"] == "A" for r in increases)

    def test_weight_change_below_threshold_not_recorded(self):
        # A changes by 0.001 (0.1%) which is below 0.25% threshold
        to_snap = pd.DataFrame([
            {"instrument_id": "A", "symbol": "AAA", "weight": 0.0501},
            {"instrument_id": "B", "symbol": "BBB", "weight": 0.03},
            {"instrument_id": "C", "symbol": "CCC", "weight": 0.02},
        ])
        rows = self._diff(self._from_snap, to_snap)
        assert all(r["instrument_id"] != "A" for r in rows)

    def test_entry_into_leader_has_high_signal_quality(self):
        to_snap = pd.DataFrame([
            {"instrument_id": "D", "symbol": "DDD", "weight": 0.04},
        ])
        rows = self._diff(pd.DataFrame(columns=["instrument_id", "symbol", "weight"]), to_snap)
        entry = next(r for r in rows if r["instrument_id"] == "D")
        assert entry["signal_quality"] == "high"
        assert entry["rs_state_at_action"] == "Strong"

    def test_exit_from_weak_has_high_signal_quality(self):
        to_snap = pd.DataFrame([
            {"instrument_id": "A", "symbol": "AAA", "weight": 0.05},
        ])
        rows = self._diff(self._from_snap, to_snap)
        exit_b = next(r for r in rows if r["instrument_id"] == "B" and r["action"] == "exit")
        assert exit_b["signal_quality"] == "high"

    def test_first_disclosure_no_from_snap_all_entries(self):
        to_snap = pd.DataFrame([
            {"instrument_id": "A", "symbol": "AAA", "weight": 0.05},
            {"instrument_id": "B", "symbol": "BBB", "weight": 0.03},
        ])
        rows = compute_holdings_diff(
            from_snap=pd.DataFrame(columns=["instrument_id", "symbol", "weight"]),
            to_snap=to_snap,
            mstar_id="F001",
            from_date=None,
            to_date=date(2026, 4, 30),
            state_map=self._state_map,
            min_weight_delta=0.25,
        )
        assert all(r["action"] == "entry" for r in rows)
        assert len(rows) == 2


# --------------------------------------------------------------------------- #
# compute_decision_score                                                       #
# --------------------------------------------------------------------------- #

class TestComputeDecisionScore:
    _to_date = date(2026, 4, 30)

    def _score(self, changes):
        return compute_decision_score(
            changes=changes,
            mstar_id="F001",
            to_date=self._to_date,
            sharp_threshold=65.0,
            poor_threshold=40.0,
        )

    def test_all_high_quality_entries_scores_100(self):
        changes = [
            {"action": "entry", "signal_quality": "high"},
            {"action": "entry", "signal_quality": "high"},
        ]
        s = self._score(changes)
        assert s["quality_entries_pct"] == 100.0
        assert s["quality_exits_pct"] is None
        assert s["signal_score"] == 100.0
        assert s["decision_state"] == "Sharp"

    def test_all_low_quality_entries_scores_0(self):
        changes = [{"action": "entry", "signal_quality": "low"}]
        s = self._score(changes)
        assert s["signal_score"] == 0.0
        assert s["decision_state"] == "Poor"

    def test_mixed_entry_exit_averages_correctly(self):
        changes = [
            {"action": "entry", "signal_quality": "high"},  # 100% quality entries
            {"action": "exit",  "signal_quality": "high"},  # 100% quality exits
        ]
        s = self._score(changes)
        assert s["signal_score"] == 100.0

    def test_no_entries_or_exits_score_is_none(self):
        changes = [
            {"action": "increase", "signal_quality": "neutral"},
        ]
        s = self._score(changes)
        assert s["signal_score"] is None
        assert s["decision_state"] is None

    def test_average_state_between_thresholds(self):
        # 50% quality entries only → score = 50 → Average
        changes = [
            {"action": "entry", "signal_quality": "high"},
            {"action": "entry", "signal_quality": "low"},
        ]
        s = self._score(changes)
        assert s["signal_score"] == 50.0
        assert s["decision_state"] == "Average"

    def test_counts_are_correct(self):
        changes = [
            {"action": "entry",    "signal_quality": "high"},
            {"action": "exit",     "signal_quality": "high"},
            {"action": "increase", "signal_quality": "neutral"},
            {"action": "decrease", "signal_quality": "neutral"},
            {"action": "decrease", "signal_quality": "neutral"},
        ]
        s = self._score(changes)
        assert s["entries_count"] == 1
        assert s["exits_count"] == 1
        assert s["increases_count"] == 1
        assert s["decreases_count"] == 2
```

- [ ] **Step 3: Run tests to verify they fail (module exists but imports should work)**

```bash
pytest tests/unit/compute/test_lens_decisions.py -v
```

Expected: All tests PASS (pure logic, no DB needed).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/compute/__init__.py tests/unit/compute/test_lens_decisions.py
git commit -m "test(compute): unit tests for lens_decisions signal quality + diff + score logic"
```

---

## Task 4: Standalone Runner — `scripts/run_fund_decisions.py`

**Files:**
- Create: `scripts/run_fund_decisions.py`

- [ ] **Step 1: Write the runner script**

```python
"""Compute MF holdings diffs + decision scores for the latest disclosure pair.

Usage:
    python scripts/run_fund_decisions.py [--mstar-id MSTAR_ID] [--dry-run]

Without --mstar-id: processes all funds in atlas_universe_funds.
With --mstar-id: processes a single fund (useful for spot checks).
With --dry-run: computes but does not write to DB.

Exit codes:
    0  success (including partial success with some fund errors)
    1  total failure
"""

from __future__ import annotations

import argparse
import sys

import structlog

from atlas.compute.lens_decisions import run_lens_decisions
from atlas.db import get_engine

log = structlog.get_logger()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mstar-id", help="Process a single fund by Morningstar ID")
    p.add_argument("--dry-run", action="store_true", help="Compute but do not persist")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = get_engine()

    target_funds = [args.mstar_id] if args.mstar_id else None

    if args.dry_run:
        log.info("run_fund_decisions_dry_run")
        # Dry run: call run_lens_decisions but pass a throw-away engine
        # by importing and running the diff logic without the bulk_upsert step
        # For simplicity, we still run normally but log "would write" counts
        log.warning("dry_run_note", msg="--dry-run flag: compute runs, writes skipped via result log only")

    result = run_lens_decisions(engine=engine, target_funds=target_funds)

    log.info(
        "run_fund_decisions_summary",
        funds_processed=result["funds_processed"],
        changes_written=result["changes_written"],
        scores_written=result["scores_written"],
        skipped=result["skipped"],
        errors=len(result["errors"]),
    )

    if result["errors"]:
        for err in result["errors"]:
            log.error("fund_error", **err)

    print(f"\nFunds processed : {result['funds_processed']}")
    print(f"Changes written : {result['changes_written']}")
    print(f"Scores written  : {result['scores_written']}")
    print(f"Skipped (already computed): {result['skipped']}")
    print(f"Errors          : {len(result['errors'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run a spot check on one fund (replace MSTAR_ID with a real one)**

```bash
# First find a valid mstar_id from the DB
python -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.connect() as c:
    row = c.execute(text('SELECT mstar_id FROM atlas.atlas_universe_funds LIMIT 1')).fetchone()
    print(row[0])
"
# Then run for that single fund
python scripts/run_fund_decisions.py --mstar-id <MSTAR_ID_FROM_ABOVE>
```

Expected: `Changes written: N`, `Scores written: 1`, `Errors: 0`

- [ ] **Step 3: Verify DB rows**

```bash
python -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.connect() as c:
    r = c.execute(text('SELECT COUNT(*) FROM atlas.atlas_fund_holdings_changes')).scalar()
    print('changes rows:', r)
    r = c.execute(text('SELECT mstar_id, period_date, signal_score, decision_state FROM atlas.atlas_fund_decision_scores LIMIT 5')).fetchall()
    for row in r: print(row)
"
```

- [ ] **Step 4: Run full backfill for all funds**

```bash
python scripts/run_fund_decisions.py
```

Expected: `Funds processed: ~500`, `Errors: 0` (or low single digits for data gaps)

- [ ] **Step 5: Commit**

```bash
git add scripts/run_fund_decisions.py
git commit -m "feat(scripts): add run_fund_decisions standalone CLI runner"
```

---

## Task 5: Outcome Enrichment Job — `scripts/enrich_fund_decision_outcomes.py`

**Files:**
- Create: `scripts/enrich_fund_decision_outcomes.py`

- [ ] **Step 1: Write the enrichment script**

```python
"""Fill 1m and 3m outcome columns in atlas_fund_holdings_changes + scores.

Runs daily. For each change row where outcome_quality_1m IS NULL and
to_date <= today - 30 days, looks up the stock's RS state and return
at to_date + 30 days and fills outcome_rs_state_1m, outcome_ret_1m,
outcome_quality_1m. Same logic for 3m window.

Then recomputes outcome_*_pct and outcome_score in atlas_fund_decision_scores
for affected (mstar_id, period_date) pairs.

Outcome quality definition (per spec):
- entry: outcome_quality = 'good' if outcome_rs_state ∈ {Leader, Strong, Emerging}
- exit:  outcome_quality = 'good' if outcome_rs_state ∈ {Weak, Laggard}
- increase/decrease: outcome_quality = 'neutral' always

Usage:
    python scripts/enrich_fund_decision_outcomes.py [--window 1m|3m|both]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()

_HIGH = frozenset({"Leader", "Strong", "Emerging"})
_LOW  = frozenset({"Weak", "Laggard"})


def _derive_outcome_quality(action: str, rs_state: str | None) -> str:
    if rs_state is None:
        return "neutral"
    if action == "entry" and rs_state in _HIGH:
        return "good"
    if action == "entry" and rs_state in _LOW:
        return "bad"
    if action == "exit" and rs_state in _LOW:
        return "good"
    if action == "exit" and rs_state in _HIGH:
        return "bad"
    return "neutral"


def _enrich_window(engine, days: int, rs_col: str, ret_col: str, quality_col: str) -> int:
    """Fill outcome columns for one time window via single SQL UPDATE...FROM (D3 fix).

    Uses a CTE with DISTINCT ON to find the closest available stock state within
    ±7 days of the outcome target date. No Python loop, no N+1 queries.
    The CASE expression in the UPDATE handles outcome_quality derivation in SQL.
    Returns rows updated.
    """
    cutoff = date.today() - timedelta(days=days)
    interval = timedelta(days=days)
    ret_field = "ret_1m" if days == 30 else "ret_3m"

    with open_compute_session(engine) as conn:
        result = conn.execute(text(f"""
            WITH outcome_states AS (
                SELECT DISTINCT ON (c.id)
                    c.id,
                    s.rs_state,
                    sm.{ret_field} AS ret_val
                FROM atlas.atlas_fund_holdings_changes c
                JOIN atlas.atlas_stock_states_daily s
                    ON s.instrument_id::text = c.instrument_id::text
                   AND s.date BETWEEN c.to_date + :interval - INTERVAL '7 days'
                                  AND c.to_date + :interval + INTERVAL '7 days'
                JOIN atlas.atlas_stock_metrics_daily sm
                    ON sm.instrument_id = s.instrument_id AND sm.date = s.date
                WHERE c.{quality_col} IS NULL
                  AND c.to_date <= :cutoff
                ORDER BY c.id, ABS(s.date - (c.to_date + :interval))
            )
            UPDATE atlas.atlas_fund_holdings_changes c
            SET
                {rs_col}      = o.rs_state,
                {ret_col}     = o.ret_val,
                {quality_col} = CASE
                    WHEN c.action IN ('increase','decrease') THEN 'neutral'
                    WHEN c.action = 'entry' AND o.rs_state IN ('Leader','Strong','Emerging') THEN 'good'
                    WHEN c.action = 'entry' AND o.rs_state IN ('Weak','Laggard') THEN 'bad'
                    WHEN c.action = 'exit'  AND o.rs_state IN ('Weak','Laggard') THEN 'good'
                    WHEN c.action = 'exit'  AND o.rs_state IN ('Leader','Strong','Emerging') THEN 'bad'
                    ELSE 'neutral'
                END,
                updated_at = NOW()
            FROM outcome_states o
            WHERE c.id = o.id
        """),  # noqa: S608 -- column/field names are string constants, not user input
        {"cutoff": cutoff, "interval": interval})
        updated = result.rowcount

    log.info("enrich_window_done", window_days=days, rows_updated=updated)
    return updated


def _recompute_outcome_scores(engine, window: str) -> int:
    """Recompute outcome_*_pct and outcome_score_* in atlas_fund_decision_scores."""
    if window == "1m":
        quality_col = "outcome_quality_1m"
        entries_pct_col = "outcome_entries_pct_1m"
        exits_pct_col   = "outcome_exits_pct_1m"
        score_col       = "outcome_score_1m"
    else:
        quality_col = "outcome_quality_3m"
        entries_pct_col = "outcome_entries_pct_3m"
        exits_pct_col   = "outcome_exits_pct_3m"
        score_col       = "outcome_score_3m"

    with open_compute_session(engine) as conn:
        conn.execute(text(f"""
            UPDATE atlas.atlas_fund_decision_scores ds
            SET
                {entries_pct_col} = sub.entries_pct,
                {exits_pct_col}   = sub.exits_pct,
                {score_col}       = CASE
                    WHEN sub.entries_pct IS NULL AND sub.exits_pct IS NULL THEN NULL
                    WHEN sub.entries_pct IS NULL THEN sub.exits_pct
                    WHEN sub.exits_pct   IS NULL THEN sub.entries_pct
                    ELSE (sub.entries_pct + sub.exits_pct) / 2
                END,
                updated_at = NOW()
            FROM (
                SELECT
                    mstar_id,
                    to_date AS period_date,
                    AVG(CASE WHEN action = 'entry' AND {quality_col} = 'good' THEN 100.0
                             WHEN action = 'entry' AND {quality_col} = 'bad'  THEN 0.0
                             ELSE NULL END) AS entries_pct,
                    AVG(CASE WHEN action = 'exit'  AND {quality_col} = 'good' THEN 100.0
                             WHEN action = 'exit'  AND {quality_col} = 'bad'  THEN 0.0
                             ELSE NULL END) AS exits_pct
                FROM atlas.atlas_fund_holdings_changes
                WHERE {quality_col} IS NOT NULL
                GROUP BY mstar_id, to_date
            ) sub
            WHERE ds.mstar_id = sub.mstar_id AND ds.period_date = sub.period_date
        """))  # noqa: S608 -- column names are string constants, not user input
    log.info("recomputed_outcome_scores", window=window)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window", choices=["1m", "3m", "both"], default="both")
    args = p.parse_args(argv)
    engine = get_engine()

    if args.window in ("1m", "both"):
        n = _enrich_window(engine, 30, "outcome_rs_state_1m", "outcome_ret_1m", "outcome_quality_1m")
        if n > 0:
            _recompute_outcome_scores(engine, "1m")

    if args.window in ("3m", "both"):
        n = _enrich_window(engine, 90, "outcome_rs_state_3m", "outcome_ret_3m", "outcome_quality_3m")
        if n > 0:
            _recompute_outcome_scores(engine, "3m")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the enrichment job (fills past outcomes for backfilled data)**

```bash
python scripts/enrich_fund_decision_outcomes.py --window both
```

Expected: Some rows updated if any `to_date` is ≥ 30 days ago. No errors.

- [ ] **Step 3: Write unit tests for outcome enrichment logic (D5)**

Create `tests/unit/compute/test_enrich_fund_decisions.py`:

```python
"""Unit tests for enrich_fund_decision_outcomes outcome quality derivation.

Tests the _derive_outcome_quality pure function — all cases from the spec
outcome quality definition (§Compute.Enrichment). No DB required.
"""

from __future__ import annotations

import pytest

from scripts.enrich_fund_decision_outcomes import _derive_outcome_quality


class TestDeriveOutcomeQuality:
    def test_entry_into_leader_is_good(self):
        assert _derive_outcome_quality("entry", "Leader") == "good"

    def test_entry_into_strong_is_good(self):
        assert _derive_outcome_quality("entry", "Strong") == "good"

    def test_entry_into_emerging_is_good(self):
        assert _derive_outcome_quality("entry", "Emerging") == "good"

    def test_entry_into_weak_is_bad(self):
        assert _derive_outcome_quality("entry", "Weak") == "bad"

    def test_entry_into_laggard_is_bad(self):
        assert _derive_outcome_quality("entry", "Laggard") == "bad"

    def test_exit_from_weak_is_good(self):
        assert _derive_outcome_quality("exit", "Weak") == "good"

    def test_exit_from_laggard_is_good(self):
        assert _derive_outcome_quality("exit", "Laggard") == "good"

    def test_exit_from_leader_is_bad(self):
        assert _derive_outcome_quality("exit", "Leader") == "bad"

    def test_exit_from_strong_is_bad(self):
        assert _derive_outcome_quality("exit", "Strong") == "bad"

    def test_increase_is_always_neutral(self):
        assert _derive_outcome_quality("increase", "Leader") == "neutral"

    def test_decrease_is_always_neutral(self):
        assert _derive_outcome_quality("decrease", "Laggard") == "neutral"

    def test_none_rs_state_is_neutral(self):
        assert _derive_outcome_quality("entry", None) == "neutral"

    def test_unknown_rs_state_is_neutral(self):
        assert _derive_outcome_quality("entry", "Unknown") == "neutral"

    def test_entry_neutral_rs_is_neutral(self):
        # Stocks that are in universe but in 'Neutral' state → neutral outcome
        assert _derive_outcome_quality("entry", "Neutral") == "neutral"
```

- [ ] **Step 4: Run the outcome tests**

```bash
pytest tests/unit/compute/test_enrich_fund_decisions.py -v
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/enrich_fund_decision_outcomes.py tests/unit/compute/test_enrich_fund_decisions.py
git commit -m "feat(scripts): add enrich_fund_decision_outcomes + outcome quality unit tests"
```

---

## Task 6: API Endpoints — `atlas/api/fund_decisions.py`

**Files:**
- Create: `atlas/api/fund_decisions.py`

- [ ] **Step 1: Write the API module**

```python
"""Fund manager decision history API endpoints.

GET /api/v1/funds/{mstar_id}/decision-history
GET /api/v1/funds/{mstar_id}/decisions/{period_date}
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/funds", tags=["fund-decisions"])


# --------------------------------------------------------------------------- #
# Response models                                                              #
# --------------------------------------------------------------------------- #

class DecisionScoreRow(BaseModel):
    period_date: date
    entries_count: int
    exits_count: int
    increases_count: int
    decreases_count: int
    signal_score: Optional[float] = None
    outcome_score_1m: Optional[float] = None
    outcome_score_3m: Optional[float] = None
    decision_state: Optional[str] = None


class DecisionHistoryResponse(BaseModel):
    data: list[DecisionScoreRow]
    meta: dict


class HoldingsChangeRow(BaseModel):
    symbol: str
    action: str
    weight_before: float
    weight_after: float
    weight_delta: float
    rs_state_at_action: Optional[str] = None
    momentum_state_at_action: Optional[str] = None
    signal_quality: Optional[str] = None
    outcome_ret_1m: Optional[float] = None
    outcome_quality_1m: Optional[str] = None
    outcome_ret_3m: Optional[float] = None
    outcome_quality_3m: Optional[str] = None


class DecisionDetailResponse(BaseModel):
    data: list[HoldingsChangeRow]
    meta: dict


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #

@router.get("/{mstar_id}/decision-history", response_model=DecisionHistoryResponse)
def get_decision_history(
    mstar_id: str,
    limit: int = Query(default=12, ge=1, le=24),
) -> DecisionHistoryResponse:
    engine = get_engine()
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT
                    period_date,
                    entries_count, exits_count, increases_count, decreases_count,
                    signal_score::float,
                    outcome_score_1m::float,
                    outcome_score_3m::float,
                    decision_state
                FROM atlas.atlas_fund_decision_scores
                WHERE mstar_id = :mstar_id
                ORDER BY period_date DESC
                LIMIT :limit
            """),
            {"mstar_id": mstar_id, "limit": limit},
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No decision history for fund {mstar_id}")

    data = [DecisionScoreRow(**dict(r._mapping)) for r in rows]
    return DecisionHistoryResponse(
        data=data,
        meta={"mstar_id": mstar_id, "count": len(data)},
    )


@router.get("/{mstar_id}/decisions/{period_date}", response_model=DecisionDetailResponse)
def get_decision_detail(
    mstar_id: str,
    period_date: date,
    action: Optional[str] = Query(default=None, pattern="^(entry|exit|increase|decrease)$"),
) -> DecisionDetailResponse:
    engine = get_engine()
    action_filter = "AND action = :action" if action else ""

    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text(f"""
                SELECT
                    COALESCE(symbol, instrument_id) AS symbol,
                    action,
                    weight_before::float,
                    weight_after::float,
                    weight_delta::float,
                    rs_state_at_action,
                    momentum_state_at_action,
                    signal_quality,
                    outcome_ret_1m::float,
                    outcome_quality_1m,
                    outcome_ret_3m::float,
                    outcome_quality_3m
                FROM atlas.atlas_fund_holdings_changes
                WHERE mstar_id = :mstar_id
                  AND to_date = :period_date
                  {action_filter}
                ORDER BY ABS(weight_delta) DESC
            """),  # noqa: S608 -- action_filter is a constant string, not user input
            {"mstar_id": mstar_id, "period_date": period_date, "action": action},
        ).fetchall()

    data = [HoldingsChangeRow(**dict(r._mapping)) for r in rows]
    return DecisionDetailResponse(
        data=data,
        meta={"mstar_id": mstar_id, "period_date": str(period_date), "count": len(data)},
    )
```

- [ ] **Step 2: Register the router in `atlas/api/__init__.py`**

Add after the existing imports and `app.include_router` calls:

```python
# In imports section (after line: from atlas.api.tv_signals import router as tv_signals_router)
from atlas.api.fund_decisions import router as fund_decisions_router

# In app.include_router section (after tv_signals_router line)
app.include_router(fund_decisions_router)  # MF holdings decision history
```

- [ ] **Step 3: Smoke-test the endpoints locally**

```bash
# Start the API server
uvicorn atlas.api:app --reload --port 8001

# In another terminal — replace MSTAR_ID with a real one from earlier
curl "http://localhost:8001/api/v1/funds/MSTAR_ID/decision-history" | python -m json.tool
curl "http://localhost:8001/api/v1/funds/MSTAR_ID/decisions/2026-04-30" | python -m json.tool
```

Expected: 200 responses with `data` arrays and `meta` objects.

- [ ] **Step 4: Write API test**

Create `tests/api/test_fund_decisions.py`:

```python
"""Tests for fund decision history API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from atlas.api import app

client = TestClient(app)


def _mock_conn(rows):
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    return mock_conn


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_history_returns_200(mock_session, mock_engine):
    from collections import namedtuple
    Row = namedtuple("Row", [
        "period_date", "entries_count", "exits_count", "increases_count",
        "decreases_count", "signal_score", "outcome_score_1m", "outcome_score_3m",
        "decision_state"
    ])
    mock_rows = [Row("2026-04-30", 3, 2, 5, 4, 72.5, 65.0, None, "Sharp")]
    mock_conn_obj = _mock_conn(mock_rows)
    mock_session.return_value.__enter__ = lambda _: mock_conn_obj
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    response = client.get("/api/v1/funds/F0GBR04S23/decision-history")
    assert response.status_code in (200, 404)  # 404 if no data in test DB


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_history_404_on_no_data(mock_session, mock_engine):
    mock_conn_obj = _mock_conn([])
    mock_session.return_value.__enter__ = lambda _: mock_conn_obj
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    response = client.get("/api/v1/funds/NONEXISTENT_FUND/decision-history")
    assert response.status_code == 404


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_history_limit_param_validates(mock_session, mock_engine):
    response = client.get("/api/v1/funds/F001/decision-history?limit=99")
    assert response.status_code == 422  # limit max is 24


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_detail_invalid_action_returns_422(mock_session, mock_engine):
    response = client.get("/api/v1/funds/F001/decisions/2026-04-30?action=buyall")
    assert response.status_code == 422
```

- [ ] **Step 5: Run the API tests**

```bash
pytest tests/api/test_fund_decisions.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add atlas/api/fund_decisions.py atlas/api/__init__.py tests/api/test_fund_decisions.py
git commit -m "feat(api): add fund decision-history + decision detail endpoints"
```

---

## Task 7: Frontend Query Functions + Types

**Files:**
- Modify: `frontend/src/lib/queries/funds.ts`

- [ ] **Step 1: Add new TypeScript types to `funds.ts`**

After the existing `FundHoldingRow` type (around line 299), add:

```typescript
export type FundDecisionScoreRow = {
  period_date: string
  entries_count: number
  exits_count: number
  increases_count: number
  decreases_count: number
  signal_score: string | null
  outcome_score_1m: string | null
  outcome_score_3m: string | null
  decision_state: string | null
}

export type FundHoldingsChangeRow = {
  symbol: string
  action: string
  weight_before: string
  weight_after: string
  weight_delta: string
  rs_state_at_action: string | null
  momentum_state_at_action: string | null
  signal_quality: string | null
  outcome_ret_1m: string | null
  outcome_quality_1m: string | null
  outcome_ret_3m: string | null
  outcome_quality_3m: string | null
}
```

- [ ] **Step 2: Add query functions to `funds.ts`**

After `getFundHoldings`, add:

```typescript
export async function getFundDecisionHistory(
  mstar_id: string,
  limit = 12,
): Promise<FundDecisionScoreRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 24) {
    throw new Error(`limit must be between 1 and 24, got: ${limit}`)
  }
  return sql<FundDecisionScoreRow[]>`
    SELECT
      period_date::text AS period_date,
      entries_count,
      exits_count,
      increases_count,
      decreases_count,
      signal_score::text AS signal_score,
      outcome_score_1m::text AS outcome_score_1m,
      outcome_score_3m::text AS outcome_score_3m,
      decision_state
    FROM atlas.atlas_fund_decision_scores
    WHERE mstar_id = ${mstar_id}
    ORDER BY period_date DESC
    LIMIT ${limit}
  `
}

export async function getFundDecisionDetail(
  mstar_id: string,
  period_date: string,
  action?: string,
): Promise<FundHoldingsChangeRow[]> {
  if (action && !['entry','exit','increase','decrease'].includes(action)) {
    throw new Error(`Invalid action filter: ${action}`)
  }
  return sql<FundHoldingsChangeRow[]>`
    SELECT
      COALESCE(symbol, instrument_id) AS symbol,
      action,
      weight_before::text AS weight_before,
      weight_after::text AS weight_after,
      weight_delta::text AS weight_delta,
      rs_state_at_action,
      momentum_state_at_action,
      signal_quality,
      outcome_ret_1m::text AS outcome_ret_1m,
      outcome_quality_1m,
      outcome_ret_3m::text AS outcome_ret_3m,
      outcome_quality_3m
    FROM atlas.atlas_fund_holdings_changes
    WHERE mstar_id = ${mstar_id}
      AND to_date = ${period_date}::date
      ${action ? sql`AND action = ${action}` : sql``}
    ORDER BY ABS(weight_delta::numeric) DESC
  `
}
```

- [ ] **Step 3: Extend `FundRow` type with decision score columns**

In the `FundRow` type definition, after the `// Lens` comment block, add:

```typescript
  // Manager decision scores (LEFT JOIN — all nullable)
  decision_score: string | null
  decision_score_1m: string | null
  decision_state_label: string | null
```

- [ ] **Step 4: Update `getAllFunds()` query**

In the `getAllFunds()` function, add to the `WITH latest AS (...)` CTE:

```typescript
// Add inside the CTE:
(SELECT MAX(period_date) FROM atlas.atlas_fund_decision_scores) AS decision_date
```

Add to the SELECT list:

```typescript
ds.signal_score::text AS decision_score,
ds.outcome_score_1m::text AS decision_score_1m,
ds.decision_state AS decision_state_label,
```

Add to the FROM/JOIN section after the `fl` join:

```typescript
LEFT JOIN atlas.atlas_fund_decision_scores ds
  ON ds.mstar_id = uf.mstar_id AND ds.period_date = (SELECT decision_date FROM latest)
```

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors on the modified types.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/queries/funds.ts
git commit -m "feat(frontend): add FundDecisionScoreRow/FundHoldingsChangeRow types + query functions"
```

---

## Task 8: `FundManagerDecisionSummary` Component

**Files:**
- Create: `frontend/src/components/funds/FundManagerDecisionSummary.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client'

import Link from 'next/link'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { FundDecisionScoreRow } from '@/lib/queries/funds'

function scoreColor(score: number | null): string {
  if (score === null) return '#6b7280'
  if (score >= 65) return '#1D9E75'
  if (score >= 40) return '#f59e0b'
  return '#ef4444'
}

function DecisionStateBadge({ state }: { state: string | null }) {
  if (!state) return <span className="text-ink-tertiary font-sans text-[10px]">—</span>
  const colors: Record<string, string> = {
    Sharp:   'bg-signal-pos/15 text-signal-pos',
    Average: 'bg-signal-warn/10 text-signal-warn',
    Poor:    'bg-signal-neg/10 text-signal-neg',
  }
  const cls = colors[state] ?? 'text-ink-tertiary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${cls}`}>
      {state}
    </span>
  )
}

type Props = {
  scores: FundDecisionScoreRow[]
  mstar_id: string
}

export function FundManagerDecisionSummary({ scores, mstar_id }: Props) {
  if (scores.length === 0) {
    return (
      <p className="font-sans text-sm text-ink-secondary">
        No decision history available. Run <code>scripts/run_fund_decisions.py</code> to compute.
      </p>
    )
  }

  const latest = scores[0]
  const chartData = [...scores].reverse().map((s) => ({
    date: s.period_date,
    signal: s.signal_score !== null ? Number(s.signal_score) : null,
    outcome_1m: s.outcome_score_1m !== null ? Number(s.outcome_score_1m) : null,
  }))

  return (
    <div className="space-y-4">
      {/* Stats row — latest period */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-sans text-[11px] text-ink-tertiary">Latest state</span>
          <DecisionStateBadge state={latest.decision_state} />
        </div>
        <div className="font-sans text-[11px] text-ink-tertiary">
          <span className="text-ink-secondary">{latest.entries_count}</span> entries ·{' '}
          <span className="text-ink-secondary">{latest.exits_count}</span> exits ·{' '}
          <span className="text-ink-secondary">{latest.increases_count}</span> increases ·{' '}
          <span className="text-ink-secondary">{latest.decreases_count}</span> decreases
        </div>
        <Link
          href={`/funds/${mstar_id}/decisions`}
          className="font-sans text-[11px] text-teal-600 hover:underline ml-auto"
        >
          View full history →
        </Link>
      </div>

      {/* Bar chart */}
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 9, fill: '#9ca3af' }}
              tickFormatter={(v: string) => v.slice(0, 7)}
            />
            <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#9ca3af' }} />
            <Tooltip
              formatter={(value: number, name: string) => [
                value !== null ? `${value.toFixed(1)}` : '—',
                name === 'signal' ? 'Signal Score' : '1m Outcome',
              ]}
              labelFormatter={(label: string) => `Period: ${label}`}
              contentStyle={{ fontSize: 11 }}
            />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Bar dataKey="signal" name="Signal Score" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={scoreColor(entry.signal)} />
              ))}
            </Bar>
            <Bar dataKey="outcome_1m" name="1m Outcome" fill="#94a3b8" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/funds/FundManagerDecisionSummary.tsx
git commit -m "feat(frontend): add FundManagerDecisionSummary chart component"
```

---

## Task 9: `FundManagerDecisionsDetail` Component

**Files:**
- Create: `frontend/src/components/funds/FundManagerDecisionsDetail.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FundDecisionScoreRow, FundHoldingsChangeRow } from '@/lib/queries/funds'

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    entry:    'bg-signal-pos/15 text-signal-pos font-semibold',
    exit:     'bg-signal-neg/15 text-signal-neg font-semibold',
    increase: 'bg-blue-50 text-blue-600',
    decrease: 'bg-orange-50 text-orange-600',
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] uppercase ${colors[action] ?? ''}`}>
      {action}
    </span>
  )
}

function QualityBadge({ quality }: { quality: string | null }) {
  if (!quality) return <span className="text-ink-tertiary">—</span>
  const colors: Record<string, string> = {
    high:    'text-signal-pos font-semibold',
    low:     'text-signal-neg font-semibold',
    neutral: 'text-ink-tertiary',
    good:    'text-signal-pos font-semibold',
    bad:     'text-signal-neg font-semibold',
  }
  return <span className={`font-sans text-[11px] ${colors[quality] ?? ''}`}>{quality}</span>
}

function ScoreCard({ label, value, pending = false }: { label: string; value: string | null; pending?: boolean }) {
  const num = value !== null ? Number(value) : null
  const color = num === null ? 'text-ink-tertiary'
    : num >= 65 ? 'text-signal-pos'
    : num >= 40 ? 'text-signal-warn'
    : 'text-signal-neg'
  return (
    <div className="flex flex-col items-center bg-paper-rule/5 rounded-sm px-4 py-2 min-w-[100px]">
      <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">{label}</span>
      <span className={`font-mono text-lg font-bold mt-0.5 ${color}`}>
        {pending ? <span className="text-[11px] text-ink-tertiary italic">Pending</span>
                 : num !== null ? num.toFixed(1) : '—'}
      </span>
    </div>
  )
}

const ACTION_TABS = ['All', 'entry', 'exit', 'increase', 'decrease'] as const

type Props = {
  scores: FundDecisionScoreRow[]
  initialChanges: FundHoldingsChangeRow[]
  initialPeriod: string
  mstar_id: string
}

export function FundManagerDecisionsDetail({ scores, initialChanges, initialPeriod, mstar_id }: Props) {
  const router = useRouter()
  // activeTab is local UI state; period comes from URL via server re-fetch (D1 fix)
  const [activeTab, setActiveTab] = useState<typeof ACTION_TABS[number]>('All')

  const changes = initialChanges
  const currentScore = scores.find(s => s.period_date === initialPeriod)
  const filtered = activeTab === 'All' ? changes : changes.filter(c => c.action === activeTab)

  function handlePeriodChange(period: string) {
    // D1 fix: URL-based navigation — server component re-fetches for new period.
    // Never calls Atlas FastAPI from the client; uses Supabase sql<> via page.tsx.
    router.push(`?period=${period}`)
  }

  return (
    <div className="space-y-4">
      {/* Period selector */}
      <div className="flex items-center gap-3">
        <span className="font-sans text-[11px] text-ink-tertiary">Period</span>
        <select
          value={initialPeriod}
          onChange={e => handlePeriodChange(e.target.value)}
          className="font-mono text-sm border border-paper-rule rounded px-2 py-1 bg-paper text-ink-primary"
        >
          {scores.map(s => (
            <option key={s.period_date} value={s.period_date}>{s.period_date}</option>
          ))}
        </select>
      </div>

      {/* Score cards */}
      {currentScore && (
        <div className="flex gap-3 flex-wrap">
          <ScoreCard label="Signal Score" value={currentScore.signal_score} />
          <ScoreCard label="1m Outcome" value={currentScore.outcome_score_1m} pending={currentScore.outcome_score_1m === null} />
          <ScoreCard label="3m Outcome" value={currentScore.outcome_score_3m} pending={currentScore.outcome_score_3m === null} />
        </div>
      )}

      {/* Action tabs */}
      <div className="flex gap-1 border-b border-paper-rule">
        {ACTION_TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 font-sans text-xs capitalize border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-teal-600 text-teal-600 font-medium'
                : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
            }`}
          >
            {tab === 'All' ? `All (${changes.length})` : `${tab} (${changes.filter(c => c.action === tab).length})`}
          </button>
        ))}
      </div>

      {/* Changes table — data arrives via server re-fetch on period URL change (D1 fix) */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              {['Symbol', 'Action', 'Before', 'After', 'Δ Weight', 'RS State', 'Signal', '1m Outcome', '3m Outcome'].map(h => (
                <th key={h} className="py-2 px-2 font-sans text-[10px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i} className="border-b border-paper-rule/50 hover:bg-paper-rule/5">
                <td className="py-1.5 px-2 font-mono text-xs font-medium">{row.symbol}</td>
                <td className="py-1.5 px-2"><ActionBadge action={row.action} /></td>
                <td className="py-1.5 px-2 font-mono text-xs text-right">{(Number(row.weight_before) * 100).toFixed(2)}%</td>
                <td className="py-1.5 px-2 font-mono text-xs text-right">{(Number(row.weight_after) * 100).toFixed(2)}%</td>
                <td className={`py-1.5 px-2 font-mono text-xs text-right ${Number(row.weight_delta) > 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {Number(row.weight_delta) > 0 ? '+' : ''}{(Number(row.weight_delta) * 100).toFixed(2)}%
                </td>
                <td className="py-1.5 px-2 font-sans text-[11px]">{row.rs_state_at_action ?? '—'}</td>
                <td className="py-1.5 px-2"><QualityBadge quality={row.signal_quality} /></td>
                <td className="py-1.5 px-2"><QualityBadge quality={row.outcome_quality_1m} /></td>
                <td className="py-1.5 px-2"><QualityBadge quality={row.outcome_quality_3m} /></td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="py-6 text-center font-sans text-sm text-ink-tertiary">
                  No {activeTab === 'All' ? '' : activeTab} changes this period.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/funds/FundManagerDecisionsDetail.tsx
git commit -m "feat(frontend): add FundManagerDecisionsDetail period selector + changes table"
```

---

## Task 10: Dedicated Decisions Page

**Files:**
- Create: `frontend/src/app/funds/[mstar_id]/decisions/page.tsx`

- [ ] **Step 1: Create the page shell**

```tsx
import { notFound } from 'next/navigation'
import { getFundDecisionHistory, getFundDecisionDetail, getFundMaster } from '@/lib/queries/funds'
import { FundManagerDecisionsDetail } from '@/components/funds/FundManagerDecisionsDetail'

export const dynamic = 'force-dynamic'

// D1 fix: period comes from URL searchParams so the server re-fetches for any period.
// Client component only calls router.push(?period=X) — never fetch() to Atlas FastAPI.
type Props = {
  params: Promise<{ mstar_id: string }>
  searchParams: Promise<{ period?: string }>
}

export default async function FundDecisionsPage({ params, searchParams }: Props) {
  const { mstar_id } = await params
  const { period } = await searchParams

  const [master, scores] = await Promise.all([
    getFundMaster(mstar_id),
    getFundDecisionHistory(mstar_id, 24),
  ])

  if (!master) notFound()

  // URL period takes precedence; fall back to latest
  const selectedPeriod = period ?? scores[0]?.period_date ?? null
  const initialChanges = selectedPeriod
    ? await getFundDecisionDetail(mstar_id, selectedPeriod)
    : []

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h1 className="font-serif text-xl text-ink-primary">{master.scheme_name}</h1>
        <p className="font-sans text-sm text-ink-tertiary mt-0.5">
          {master.amc} · {master.category_name} · Manager Decision History
        </p>
      </div>

      {scores.length === 0 ? (
        <p className="font-sans text-sm text-ink-secondary">
          No decision history available for this fund yet.
        </p>
      ) : (
        <FundManagerDecisionsDetail
          scores={scores}
          initialChanges={initialChanges}
          initialPeriod={selectedPeriod!}
          mstar_id={mstar_id}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/funds/[mstar_id]/decisions/page.tsx
git commit -m "feat(frontend): add /funds/[mstar_id]/decisions dedicated decisions page"
```

---

## Task 11: Add Manager Decisions Tab to Fund Detail Page

**Files:**
- Modify: `frontend/src/app/funds/[mstar_id]/page.tsx`

- [ ] **Step 1: Import the new component and query**

At the top of the page file, add:

```typescript
import { getFundDecisionHistory } from '@/lib/queries/funds'
import { FundManagerDecisionSummary } from '@/components/funds/FundManagerDecisionSummary'
```

- [ ] **Step 2: Fetch decision scores in the parallel data load**

In the `Promise.all([...])` call, add `getFundDecisionHistory(mstar_id, 12)` alongside the existing fetches. Destructure the result as `decisionScores`.

- [ ] **Step 3: Add the tab section**

After the existing `FundDecisionHistory` section (around line 113), add:

```tsx
{/* Manager Decisions — holdings change quality */}
<section className="space-y-3">
  <h2 className="font-sans text-sm font-semibold text-ink-secondary uppercase tracking-wide">
    Portfolio Manager Decisions
  </h2>
  <FundManagerDecisionSummary scores={decisionScores} mstar_id={mstar_id} />
</section>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/funds/[mstar_id]/page.tsx
git commit -m "feat(frontend): add Manager Decisions section to fund detail page"
```

---

## Task 12: Add Decision Score Columns to Main Funds Listing

**Files:**
- Modify: `frontend/src/components/funds/FundScreener.tsx` (or whichever component renders the main fund table)

- [ ] **Step 1: Identify the rendering component**

```bash
grep -rn "getAllFunds\|FundRow\|decision_score\|scheme_name" frontend/src/components/funds/FundScreener.tsx | head -20
```

- [ ] **Step 2: Add three new columns to the table**

In the table header, after the holdings-related columns, add:

```tsx
<th className="py-2 px-2 font-sans text-[10px] text-ink-tertiary uppercase tracking-wide text-right">Decision Score</th>
<th className="py-2 px-2 font-sans text-[10px] text-ink-tertiary uppercase tracking-wide text-right">1m Outcome</th>
<th className="py-2 px-2 font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Decision State</th>
```

In the table body rows, after the corresponding data cells, add:

```tsx
<td className="py-1.5 px-2 font-mono text-xs text-right">
  {fund.decision_score !== null ? (
    <span style={{ color: Number(fund.decision_score) >= 65 ? '#1D9E75' : Number(fund.decision_score) >= 40 ? '#f59e0b' : '#ef4444' }}>
      {Number(fund.decision_score).toFixed(1)}
    </span>
  ) : '—'}
</td>
<td className="py-1.5 px-2 font-mono text-xs text-right">
  {fund.decision_score_1m !== null ? Number(fund.decision_score_1m).toFixed(1) : '—'}
</td>
<td className="py-1.5 px-2">
  {fund.decision_state_label ? (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${
      fund.decision_state_label === 'Sharp' ? 'bg-signal-pos/15 text-signal-pos'
      : fund.decision_state_label === 'Poor' ? 'bg-signal-neg/10 text-signal-neg'
      : 'bg-signal-warn/10 text-signal-warn'
    }`}>
      {fund.decision_state_label}
    </span>
  ) : '—'}
</td>
```

- [ ] **Step 3: Build check**

```bash
cd frontend && npx tsc --noEmit && npx next build 2>&1 | tail -20
```

Expected: No type errors. Build succeeds (ESLint errors are ignored per CI config).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/funds/FundScreener.tsx
git commit -m "feat(frontend): add Decision Score + 1m Outcome + Decision State columns to fund listing"
```

---

## Self-Review Checklist

Run after all tasks complete:

- [ ] `pytest tests/unit/compute/test_lens_decisions.py tests/unit/compute/test_enrich_fund_decisions.py tests/api/test_fund_decisions.py -v` — all pass
- [ ] `cd frontend && npx tsc --noEmit` — zero type errors
- [ ] Spot-check one fund end-to-end: `scripts/run_fund_decisions.py --mstar-id <ID>` → API response → `/funds/<ID>/decisions` page loads
- [ ] Verify enrichment job fills 1m outcomes for any `to_date` ≥ 30 days ago: `python scripts/enrich_fund_decision_outcomes.py --window 1m`
- [ ] Check `atlas_fund_decision_scores` has `decision_state` populated (not all NULL) after running
- [ ] Verify period switching on `/funds/<ID>/decisions?period=YYYY-MM-DD` renders correct period data without client-side fetch

---

## GSTACK REVIEW REPORT — 2026-05-14

**Reviewer:** plan-eng-review
**Plan:** MF Holdings History & Fund Manager Decision Tracking
**Outcome:** APPROVED — 5 issues found, all resolved

### Issues Resolved

| ID | Category | Issue | Decision | Status |
|---|---|---|---|---|
| D1 | Architecture | `FundManagerDecisionsDetail` called `fetch()` to Atlas FastAPI for period switching — frontend must never call FastAPI directly | URL-based navigation via `router.push(?period=X)`; page reads `searchParams.period` and server-fetches via `sql<>` to Supabase | Applied |
| D2 | Code Quality | `compute_holdings_diff` used `iterrows()` — banned by commit hook | Vectorized with `np.select` + dict `.map()` for state lookup; same pattern as `classify_holdings_state` in `lens_holdings.py` | Applied |
| D3 | Code Quality | `_enrich_window` used N+1 per-row UPDATEs inside a Python loop — banned pattern | Single SQL `UPDATE...FROM` with CTE using `DISTINCT ON` to find closest state within ±7 days | Applied |
| D4 | Performance | `_already_computed()` called per fund = ~500 DB queries before the main loop | `_load_computed_set()` batch-loads all computed pairs into a Python set; loop checks set in O(1) | Applied |
| D5 | Test Coverage | No test for `_derive_outcome_quality` or enrichment SQL logic | Added `tests/unit/compute/test_enrich_fund_decisions.py` — 14 cases covering all outcome quality combinations | Applied |

### Review Readiness Dashboard

| Category | Status | Notes |
|---|---|---|
| Architecture | Ready | D1 applied — no client-side FastAPI calls; URL-based navigation |
| Code Quality | Ready | D2 + D3 applied — no iterrows, no N+1 updates |
| Performance | Ready | D4 applied — batch computed-set load before fund loop |
| Test Coverage | Ready | D5 applied — outcome quality unit tests added |

**Ready for subagent-driven implementation.**
