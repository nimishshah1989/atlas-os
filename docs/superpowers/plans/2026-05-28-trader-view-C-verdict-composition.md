# Stream C — Verdict Composition + First-Called Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single `combined_verdict` column (BUY / ACCUMULATE / WATCH / HOLD / AVOID / SELL / WAIT) plus `verdict_reason`, `first_called_at`, and `since_call_return` to the MVs that serve the stock / ETF / sector / fund pages. The UI rebuild (stream D) reads from these columns.

**Architecture:** New Python module `atlas/verdict/derive.py` implements the precedence ladder from spec §4. Called from nightly cron after MV refresh. Writes to four MVs: `mv_stock_landscape`, `mv_etf_scorecard`, `mv_sector_cards`, `mv_fund_scorecard`. WAIT depends on Weinstein thresholds from stream A; ships with default 30W and migrates once A locks.

**Tech Stack:** PostgreSQL (Supabase), Python 3.11, SQLAlchemy 2.0 async, Decimal for money.

**Source spec:** `docs/superpowers/specs/2026-05-28-trader-view-redesign.html` §4 + §5.

---

### Task 1: Verdict derivation module

**Files:**
- Create: `atlas/verdict/__init__.py`
- Create: `atlas/verdict/derive.py`
- Test: `tests/verdict/test_derive.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/verdict/test_derive.py
import pytest
from atlas.verdict.derive import derive_verdict, VerdictInput

def test_positive_cell_stage2_all_gates_pass_not_owned_returns_BUY():
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=2, user_owns=False,
        gates={'strength': True, 'direction': True, 'risk': True, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'BUY' and v.reason is None

def test_positive_cell_stage2_all_gates_pass_owned_returns_ACCUMULATE():
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=2, user_owns=True,
        gates={'strength': True, 'direction': True, 'risk': True, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'ACCUMULATE'

def test_positive_cell_stage4_returns_WAIT():
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=4, user_owns=False,
        gates={'strength': True, 'direction': True, 'risk': True, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'WAIT'
    assert v.reason == 'Stage 4 vetoes positive cell'

def test_positive_cell_risk_gate_fail_returns_WAIT():
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=2, user_owns=False,
        gates={'strength': True, 'direction': True, 'risk': False, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'WAIT'
    assert 'risk gate' in v.reason.lower()

def test_positive_cell_stage3_not_owned_returns_WATCH():
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=3, user_owns=False,
        gates={'strength': True, 'direction': True, 'risk': True, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'WATCH'
    assert v.reason == 'Stage 3 topping'

def test_positive_cell_stage3_owned_returns_HOLD():
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=3, user_owns=True,
        gates={'strength': True, 'direction': True, 'risk': True, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'HOLD'

def test_neutral_cell_not_owned_returns_WATCH():
    v = derive_verdict(VerdictInput(cell_state='NEUTRAL', weinstein_stage=2, user_owns=False, gates={}))
    assert v.verdict == 'WATCH' and v.reason is None

def test_neutral_cell_owned_returns_HOLD():
    v = derive_verdict(VerdictInput(cell_state='NEUTRAL', weinstein_stage=2, user_owns=True, gates={}))
    assert v.verdict == 'HOLD'

def test_negative_cell_not_owned_returns_AVOID():
    v = derive_verdict(VerdictInput(cell_state='NEGATIVE', weinstein_stage=4, user_owns=False, gates={}))
    assert v.verdict == 'AVOID'

def test_negative_cell_owned_returns_SELL():
    v = derive_verdict(VerdictInput(cell_state='NEGATIVE', weinstein_stage=4, user_owns=True, gates={}))
    assert v.verdict == 'SELL'

def test_micro_cap_no_weinstein_veto():
    # Q5 spec lock: Micro defaults to no Weinstein veto regardless of stage
    v = derive_verdict(VerdictInput(
        cell_state='POSITIVE', weinstein_stage=4, user_owns=False, cap_tier='Micro',
        gates={'strength': True, 'direction': True, 'risk': True, 'sector': True, 'market': True},
    ))
    assert v.verdict == 'BUY'  # Stage 4 ignored for Micro
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os && pytest tests/verdict/ -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.verdict'`

- [ ] **Step 3: Implement the module**

```python
# atlas/verdict/__init__.py
"""Verdict composition — single source of truth for the trader-facing decision label."""
from atlas.verdict.derive import derive_verdict, VerdictInput, VerdictOutput

__all__ = ["derive_verdict", "VerdictInput", "VerdictOutput"]
```

```python
# atlas/verdict/derive.py
"""Derive the trader-facing verdict from cell state + Weinstein stage + gates + ownership.

Source of truth: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4.
Vocabulary lock: CONTEXT.md §"Cell state vocabulary" (BUY/ACCUMULATE/WATCH/HOLD/AVOID/SELL/WAIT).
Q5 lock: Micro cap-tier exempts from Weinstein veto.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

CellState = Literal['POSITIVE', 'NEUTRAL', 'NEGATIVE']
Verdict = Literal['BUY', 'ACCUMULATE', 'WATCH', 'HOLD', 'AVOID', 'SELL', 'WAIT']


@dataclass(frozen=True)
class VerdictInput:
    cell_state: CellState
    weinstein_stage: Optional[int]      # 1, 2, 3, 4, or None
    user_owns: bool
    gates: dict                          # {'strength': bool, 'direction': bool, ...}
    cap_tier: str = 'Large'              # Large / Mid / Small / Micro


@dataclass(frozen=True)
class VerdictOutput:
    verdict: Verdict
    reason: Optional[str]


def derive_verdict(inp: VerdictInput) -> VerdictOutput:
    # 1. NEGATIVE cells — ownership decides verb
    if inp.cell_state == 'NEGATIVE':
        return VerdictOutput('SELL' if inp.user_owns else 'AVOID', None)

    # 2. NEUTRAL cells — holding pattern
    if inp.cell_state == 'NEUTRAL':
        return VerdictOutput('HOLD' if inp.user_owns else 'WATCH', None)

    # 3. POSITIVE — check vetoes before promoting to BUY/ACCUMULATE
    assert inp.cell_state == 'POSITIVE'

    # 3a. Weinstein Stage 4 veto (Micro exempt per Q5 lock)
    if inp.cap_tier != 'Micro' and inp.weinstein_stage == 4:
        return VerdictOutput('WAIT', 'Stage 4 vetoes positive cell')

    # 3b. Gate veto — any fail blocks
    for gate_name, passed in inp.gates.items():
        if passed is False:
            return VerdictOutput('WAIT', f'{gate_name.replace("_", " ").title()} gate fail')

    # 3c. Stage 3 ambiguity — downgrade to WATCH/HOLD, not WAIT (Q1 lock)
    if inp.cap_tier != 'Micro' and inp.weinstein_stage == 3:
        return VerdictOutput(
            'HOLD' if inp.user_owns else 'WATCH',
            'Stage 3 topping',
        )

    # 3d. Clear path
    return VerdictOutput('ACCUMULATE' if inp.user_owns else 'BUY', None)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/verdict/ -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/verdict/ tests/verdict/
git commit -m "feat(verdict): derive_verdict() — precedence ladder per spec §4"
```

---

### Task 2: SQL helper for verdict derivation in MV

**Files:**
- Create: `migrations/versions/117_verdict_helper_function.py`

- [ ] **Step 1: Write a SQL function mirroring the Python logic**

```python
# migrations/versions/117_verdict_helper_function.py
"""SQL function atlas.derive_verdict() — mirrors atlas.verdict.derive Python module."""

from alembic import op

revision = "117_verdict_helper_function"
down_revision = "116_pg_cron_drift_nightly"

def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION atlas.derive_verdict(
          p_cell_state    text,
          p_weinstein     int,
          p_user_owns     boolean,
          p_cap_tier      text,
          p_gate_strength boolean,
          p_gate_direction boolean,
          p_gate_risk      boolean,
          p_gate_sector    boolean,
          p_gate_market    boolean
        ) RETURNS TABLE(verdict text, reason text)
        LANGUAGE plpgsql IMMUTABLE
        AS $$
        BEGIN
          -- 1. NEGATIVE
          IF p_cell_state = 'NEGATIVE' THEN
            RETURN QUERY SELECT
              CASE WHEN p_user_owns THEN 'SELL' ELSE 'AVOID' END,
              NULL::text;
            RETURN;
          END IF;

          -- 2. NEUTRAL
          IF p_cell_state = 'NEUTRAL' THEN
            RETURN QUERY SELECT
              CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END,
              NULL::text;
            RETURN;
          END IF;

          -- 3a. Weinstein Stage 4 veto (Micro exempt)
          IF p_cap_tier != 'Micro' AND p_weinstein = 4 THEN
            RETURN QUERY SELECT 'WAIT', 'Stage 4 vetoes positive cell';
            RETURN;
          END IF;

          -- 3b. Gate vetoes
          IF p_gate_strength  = false THEN RETURN QUERY SELECT 'WAIT', 'Strength gate fail';  RETURN; END IF;
          IF p_gate_direction = false THEN RETURN QUERY SELECT 'WAIT', 'Direction gate fail'; RETURN; END IF;
          IF p_gate_risk      = false THEN RETURN QUERY SELECT 'WAIT', 'Risk gate fail';      RETURN; END IF;
          IF p_gate_sector    = false THEN RETURN QUERY SELECT 'WAIT', 'Sector gate fail';    RETURN; END IF;
          IF p_gate_market    = false THEN RETURN QUERY SELECT 'WAIT', 'Market gate fail';    RETURN; END IF;

          -- 3c. Stage 3 downgrade
          IF p_cap_tier != 'Micro' AND p_weinstein = 3 THEN
            RETURN QUERY SELECT
              CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END,
              'Stage 3 topping';
            RETURN;
          END IF;

          -- 3d. Clear path
          RETURN QUERY SELECT
            CASE WHEN p_user_owns THEN 'ACCUMULATE' ELSE 'BUY' END,
            NULL::text;
        END;
        $$;
    """)

def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS atlas.derive_verdict(text, int, boolean, text, boolean, boolean, boolean, boolean, boolean);")
```

- [ ] **Step 2: Apply + smoke-test**

```bash
ssh atlas "alembic upgrade head"
```

```sql
SELECT * FROM atlas.derive_verdict('POSITIVE', 2, false, 'Large', true, true, true, true, true);
-- Expected: BUY, NULL
SELECT * FROM atlas.derive_verdict('POSITIVE', 4, false, 'Large', true, true, true, true, true);
-- Expected: WAIT, "Stage 4 vetoes positive cell"
```

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/117_verdict_helper_function.py
git commit -m "feat(verdict): atlas.derive_verdict() SQL function (mirrors Python)"
```

---

### Task 3: Add verdict columns to mv_stock_landscape

**Files:**
- Create: `migrations/versions/118_verdict_columns_stock_landscape.py`

- [ ] **Step 1: Rebuild MV with verdict + first_called + since_call_return**

```python
# migrations/versions/118_verdict_columns_stock_landscape.py

from alembic import op

revision = "118_verdict_columns_stock_landscape"
down_revision = "117_verdict_helper_function"

def upgrade() -> None:
    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_landscape CASCADE;
        CREATE MATERIALIZED VIEW atlas.mv_stock_landscape AS
        WITH base AS (
          -- existing mv_stock_landscape body … (preserved from migration 102 or wherever it lives)
          -- We add joins to: atlas_signal_calls (entry_date, predicted_excess),
          -- atlas_stock_weinstein (current stage), atlas_paper_portfolio (ownership)
          SELECT
            s.*,
            sc.signal_call_id,
            sc.entry_date           AS first_called_at,
            sc.action               AS cell_state,
            sc.predicted_excess,
            sc.sigma_predicted,
            w.stage                 AS weinstein_stage,
            pp.instrument_id IS NOT NULL AS user_owns,
            -- gate booleans from atlas_etf_scorecard or per-stock equivalent
            gs.strength_gate, gs.direction_gate, gs.risk_gate, gs.sector_gate, gs.market_gate
          FROM atlas.mv_stock_landscape_legacy s   -- the prior unmodified MV body
          LEFT JOIN atlas.atlas_signal_calls sc
                 ON sc.instrument_id = s.instrument_id AND sc.exit_date IS NULL
          LEFT JOIN atlas.atlas_stock_weinstein w
                 ON w.instrument_id = s.instrument_id AND w.as_of_date = s.as_of_date
          LEFT JOIN atlas.atlas_paper_portfolio pp
                 ON pp.instrument_id = s.instrument_id  -- Q4: paper portfolio
          LEFT JOIN atlas.mv_stock_gate_status gs
                 ON gs.instrument_id = s.instrument_id
        ),
        with_verdict AS (
          SELECT
            base.*,
            v.verdict AS combined_verdict,
            v.reason  AS verdict_reason
          FROM base, LATERAL atlas.derive_verdict(
            COALESCE(base.cell_state, 'NEUTRAL'),
            base.weinstein_stage,
            base.user_owns,
            base.cap_tier,
            base.strength_gate,
            base.direction_gate,
            base.risk_gate,
            base.sector_gate,
            base.market_gate
          ) v
        ),
        with_since_call AS (
          SELECT
            wv.*,
            (p_now.close_adj / NULLIF(p_entry.close_adj, 0) - 1) AS since_call_return
          FROM with_verdict wv
          LEFT JOIN atlas.atlas_prices_daily p_now
                 ON p_now.instrument_id = wv.instrument_id
                AND p_now.date = wv.as_of_date
          LEFT JOIN atlas.atlas_prices_daily p_entry
                 ON p_entry.instrument_id = wv.instrument_id
                AND p_entry.date = wv.first_called_at
        )
        SELECT * FROM with_since_call;

        CREATE UNIQUE INDEX uix_mv_stock_landscape_iid
          ON atlas.mv_stock_landscape (instrument_id);
    """)

def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_landscape CASCADE;")
    # restore the legacy MV here if needed
```

NOTE: The migration must preserve the existing body. Read migration 102 or wherever `mv_stock_landscape` was last defined; copy that body in place of `mv_stock_landscape_legacy`. Do **not** silently drop unused columns — every downstream consumer needs to be checked first.

- [ ] **Step 2: Apply + verify**

```bash
ssh atlas "alembic upgrade head"
```

```sql
SELECT combined_verdict, verdict_reason, COUNT(*)
FROM atlas.mv_stock_landscape
GROUP BY 1, 2
ORDER BY 3 DESC;
```

Expected distribution: WAIT and HOLD/WATCH should be present; if every stock comes back BUY or AVOID, the gate/Weinstein joins are broken.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/118_verdict_columns_stock_landscape.py
git commit -m "feat(verdict): combined_verdict + first_called_at on mv_stock_landscape"
```

---

### Task 4: Replicate for ETFs, sectors, funds

**Files:**
- Create: `migrations/versions/119_verdict_columns_etfs_sectors_funds.py`

- [ ] **Step 1: Apply the same pattern to the other three MVs**

For each of `mv_etf_scorecard`, `mv_sector_cards`, `mv_fund_scorecard`:
1. Read current definition (the migration that creates it)
2. Add `combined_verdict`, `verdict_reason`, `first_called_at`, `since_call_return` columns via the same `atlas.derive_verdict()` LATERAL join pattern
3. Note: sectors and funds don't have per-instrument signal_calls in the same way — for sectors, use the sector_state directly (Overweight → cell_state=POSITIVE; Neutral → NEUTRAL; Underweight/Avoid → NEGATIVE). For funds, derive from the underlying-holdings composite cell distribution.

Each MV gets its own migration body in this one file (do not split — they ship together).

- [ ] **Step 2: Apply + verify each MV**

```sql
SELECT 'etfs' AS source, combined_verdict, COUNT(*) FROM atlas.mv_etf_scorecard GROUP BY 2
UNION ALL
SELECT 'sectors', combined_verdict, COUNT(*) FROM atlas.mv_sector_cards GROUP BY 2
UNION ALL
SELECT 'funds', combined_verdict, COUNT(*) FROM atlas.mv_fund_scorecard GROUP BY 2;
```

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/119_verdict_columns_etfs_sectors_funds.py
git commit -m "feat(verdict): combined_verdict columns on ETF + sector + fund MVs"
```

---

### Task 5: pg_cron refresh schedule update

**Files:**
- Modify: `migrations/versions/120_pg_cron_consolidated_refresh_v2.py`

- [ ] **Step 1: Confirm verdict-MVs included in nightly refresh**

The existing `mv_refresh_v6_all` cron job (migration 111) refreshes the four MVs. Verify that each new column is automatically included (since we DROP CASCADE + CREATE), so no schedule change is needed — only a sanity check.

- [ ] **Step 2: Commit (or skip if no change)**

If no change needed:
```bash
echo "No schedule changes — verdict columns refresh as part of existing mv_refresh_v6_all"
```

---

### Definition of Done

- [ ] `atlas.derive_verdict()` Python module passes 11 unit tests
- [ ] `atlas.derive_verdict()` SQL function returns identical results on the same inputs
- [ ] `mv_stock_landscape` exposes `combined_verdict`, `verdict_reason`, `first_called_at`, `since_call_return` columns with no NULL on populated instruments
- [ ] Same columns exposed on `mv_etf_scorecard`, `mv_sector_cards`, `mv_fund_scorecard`
- [ ] Distribution check: across all stocks, at least 3 of the 7 verdict values appear (sanity — not all BUY or all AVOID)
- [ ] No frontend code depends on the legacy `action` column for top-level decisions — the verdict column is the new contract
- [ ] Q1, Q4, Q5 spec locks enforced (Stage 3 downgrade, paper portfolio ownership, Micro Weinstein exemption)
- [ ] Weinstein thresholds read from atlas_thresholds (set by stream A) once stream A lands

### Self-review checklist

- [ ] SQL function `atlas.derive_verdict()` and Python `derive_verdict()` produce identical outputs for the same inputs (Property test: pick 100 random valid inputs, assert outputs match)
- [ ] Stage 3 downgrades to WATCH/HOLD (Q1 lock), does NOT go to WAIT
- [ ] Micro cap_tier bypasses Weinstein veto (Q5 lock)
- [ ] Gate fail returns WAIT with a *named* failing gate (Risk gate fail / Direction gate fail / etc.) — never just "veto"
- [ ] No raw SQL DDL — every schema change via Alembic
- [ ] All migrations are reversible
