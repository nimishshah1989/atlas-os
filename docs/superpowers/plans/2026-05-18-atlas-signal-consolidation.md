# Atlas Signal Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate parallel signal systems by routing every page on atlas.jslwealth.in through a single SQL-view layer (`atlas_*_signal_unified`) whose values come from the IC-validated state engine. Legacy tables become read-only for a 2-week burn-in, then drop.

**Architecture:** Three layers from bottom up. (1) The IC-validated `atlas_stock_state_daily` is the only state truth. (2) Four SQL views — `atlas_stock_signal_unified` (re-derives legacy column names per row) and three bottom-up aggregators (`atlas_sector_signal_unified`, `atlas_fund_signal_unified`, `atlas_etf_signal_unified`) computed nightly from constituent stock states. (3) Frontend query files point at the views; existing pages keep working through the rewire window with no consumer-side breakage.

**Tech Stack:** Python 3.12 (atlas/intelligence/aggregations/), SQLAlchemy 2.0 + Alembic, Postgres 15, Next.js App Router (frontend), Recharts. Tests: pytest + pytest-asyncio; Vitest + React Testing Library on the frontend. Hooks enforce 400 LOC source / 800 LOC tests / 250 LOC page shells.

---

## Anchors (read before starting)

- **Spec:** [docs/superpowers/specs/2026-05-18-atlas-signal-consolidation-design.md](../specs/2026-05-18-atlas-signal-consolidation-design.md)
- **State engine spec:** [docs/superpowers/specs/2026-05-18-atlas-state-engine-design.md](../specs/2026-05-18-atlas-state-engine-design.md)
- **Phase 2 IC audit:** [docs/audits/state-engine-phase2-ic-2026-05.md](../../audits/state-engine-phase2-ic-2026-05.md)
- **Existing primitives:** `atlas/intelligence/states/classifier.py`, `atlas/intelligence/validation/ic_engine.py`, `atlas/intelligence/validation/forward_returns.py`
- **Migrations head:** 079. Phase 1 of THIS plan starts at 080.

---

## File structure

### Backend — new files
- `atlas/intelligence/aggregations/__init__.py` — package marker
- `atlas/intelligence/aggregations/base.py` — shared types + weight helper (≤80 LOC)
- `atlas/intelligence/aggregations/sector.py` — bottom-up sector state aggregator (≤300 LOC)
- `atlas/intelligence/aggregations/fund.py` — composition + holdings aggregators (≤300 LOC)
- `atlas/intelligence/aggregations/etf.py` — bottom-up ETF state aggregator (≤250 LOC)
- `atlas/intelligence/aggregations/persistence.py` — UPSERT writers for the three new aggregate tables (≤200 LOC)
- `atlas/intelligence/states/ic_harness.py` — one-shot IC runner for legacy candidate signals (CTS, nav_state, entry/exit triggers) (≤350 LOC)
- `atlas/trading/cli_consolidation.py` — `atlas-lab consolidation` subcommand group (≤200 LOC)

### Backend — modified files
- `atlas/compute/stocks.py` — disable legacy nightly write (single-line change)
- `atlas/compute/sectors.py` — replace state-classification call with aggregator call
- `atlas/compute/etfs.py` — replace state-classification call with aggregator call
- `atlas/compute/funds.py` — composition + holdings paths replaced; nav_state retained
- `atlas/trading/cli.py` — register new subcommand group
- `scripts/m2_daily.py` — wire state engine + aggregators into nightly DAG
- `scripts/m3_daily.py` — same for sector/fund cadence if separate

### Backend — migrations (Alembic, head 079 → 089)
- `migrations/versions/080_atlas_stock_signal_unified_view.py`
- `migrations/versions/081_atlas_sector_signal_unified_view.py`
- `migrations/versions/082_atlas_fund_signal_unified_view.py`
- `migrations/versions/083_atlas_etf_signal_unified_view.py`
- `migrations/versions/084_atlas_sector_state_v2_table.py` (new sector aggregate table)
- `migrations/versions/085_atlas_fund_state_v2_table.py` (new fund aggregate table)
- `migrations/versions/086_atlas_etf_state_v2_table.py` (new ETF aggregate table)
- `migrations/versions/087_legacy_signal_validation_kind.py` (extend `atlas_component_validation` with `component_kind`)
- `migrations/versions/088_drop_legacy_state_tables_phase1.py` (drop conviction + CTS — applied only after IC harness validates SP04/SP09)
- `migrations/versions/089_drop_legacy_state_tables_phase2.py` (drop atlas_stock_states_daily and aggregate state tables — applied after 2-week burn-in)

### Backend — test files
- `tests/intelligence/aggregations/__init__.py`
- `tests/intelligence/aggregations/test_base.py`
- `tests/intelligence/aggregations/test_sector.py`
- `tests/intelligence/aggregations/test_fund.py`
- `tests/intelligence/aggregations/test_etf.py`
- `tests/intelligence/aggregations/test_persistence.py`
- `tests/intelligence/states/test_ic_harness.py`
- `tests/migrations/test_signal_unified_views.py`

### Frontend — deleted files
- `frontend/src/components/ui/StateJourneyCompact.tsx`
- `frontend/src/components/stocks/SignalCell.tsx`
- `frontend/src/components/stocks/CTSDeepDiveCard.tsx`
- `frontend/src/components/stocks/CTSGradeSummaryCards.tsx`
- `frontend/src/components/stocks/CTSIndexTimingPanel.tsx`
- `frontend/src/components/stocks/CTSSectorPanel.tsx`
- `frontend/src/components/stocks/CTSSignalBadge.tsx`
- `frontend/src/components/stocks/CTSTimingCell.tsx`
- `frontend/src/components/stocks/StockHistoryTab.tsx`
- `frontend/src/components/funds/FundStateJourneyCompact.tsx`
- `frontend/src/app/api/cts/index-timing/route.ts`
- `frontend/src/app/api/cts/sectors/route.ts`
- `frontend/src/app/api/states-compact/route.ts`
- `frontend/src/app/api/fund-states-compact/route.ts`
- All corresponding `__tests__/` files for the above

### Frontend — modified files
- `frontend/src/lib/stock-formatters.tsx` — remove `StateTuple4` export + `StateBadge` legacy renderers (file already exists; this slims it)
- `frontend/src/lib/queries/stocks.ts` — point at `atlas_stock_signal_unified`
- `frontend/src/lib/queries/sectors.ts` — point at `atlas_sector_signal_unified`
- `frontend/src/lib/queries/funds.ts` — point at `atlas_fund_signal_unified`
- `frontend/src/lib/queries/etfs.ts` — point at `atlas_etf_signal_unified`
- `frontend/src/lib/queries/conviction.ts` — derive from new state engine OR delete (decided in Phase 6)
- `frontend/src/lib/queries/global.ts`, `us-stocks.ts`, `us-etfs.ts`, `us-sectors.ts`, `sector-deep-dive.ts`, `sector-funds.ts`, `instruments.ts`, `health.ts` — point at unified views
- `frontend/src/components/stocks/StockScreener.tsx` — remove 7-gate column, remove momentum/volume chips
- `frontend/src/components/stocks/StockDeepDiveBody.tsx` — remove exit-flag rendering, remove Weinstein/Momentum interpretation panels
- `frontend/src/components/stocks/StockDeepDiveHeader.tsx` — remove `StateTuple4` import
- `frontend/src/components/stocks/StockOverviewTab.tsx` — remove Weinstein/Momentum panels
- `frontend/src/components/stocks/ConvictionCell.tsx` — rename to `WithinStateRankCell.tsx`; rewires to read `within_state_rank`
- `frontend/src/components/stocks/RSLeadersPanel.tsx`, `RSStateChip.tsx` (if separate) — replace with `ValidatedBadge` derived from `rs_rank_12m`
- `frontend/src/components/sectors/SectorOverviewTab.tsx`, `SectorStocksTab.tsx`, `SectorETFTab.tsx`, `SectorDrawerSnapshot.tsx` — read aggregate from new view
- `frontend/src/components/funds/FundPageClient.tsx`, `FundScreener.tsx`, `FundHoldingsTab.tsx`, `FundDeepDiveHeader.tsx` — read from new view
- `frontend/src/components/etfs/ETFScreener.tsx`, `ETFBubbleChart.tsx`, `ETFSnapshotTiles.tsx` — read from new view; ETFBubbleChart re-axes (x=ATR ratio, y=within_state_rank, color=state)
- `frontend/src/components/global/GlobalCountryScreener.tsx`, `CountryRankingsTable.tsx` — read from new view
- `frontend/src/components/us/USSectorDetailTabs.tsx` — read from new view
- `frontend/src/app/stocks/page.tsx`, `frontend/src/app/sectors/page.tsx`, etc. — only if shells exceed 250 LOC after rewire (they shouldn't)

### Frontend — test files
- Vitest tests beside each modified component / query (existing `__tests__/` convention)

---

## Coexistence rules (NON-NEGOTIABLE)

1. **V5-RP-TREND stays rank 1.** Run `atlas-lab goal-post --rank 1` at the end of every phase. Must return `met:true`.
2. **`atlas/trading/lab.py` is read-only for this plan.** The strategy runner is untouched.
3. **No drop migrations run until Phase 9** (after 2-week burn-in verification).
4. **Bridge views are non-destructive.** Phase 1 deploys them; legacy tables still write nightly. The cutover to "state-engine-only nightly write" happens in Phase 8.
5. **Parallel-deploy isolation.** All work happens on `feat/atlas-consolidation` (worktree at `../atlas-os-consolidation`). EC2 deploys go to `/home/ubuntu/atlas-frontend-v2/` and PM2 process `atlas-frontend-v2` on port `3002`. The existing `atlas-frontend` (3001) on `atlas.jslwealth.in` is untouched until the fund-manager demo approves the v2.

---

## Phase 0 — Parallel deploy infrastructure (0.5 day CC)

Goal: stand up a second deploy target on EC2 (`/home/ubuntu/atlas-frontend-v2/`, PM2 process `atlas-frontend-v2` on port 3002, security-group rule allowing inbound :3002). All subsequent phase deploys go to this target; production atlas-frontend on :3001 is unaffected.

### Task 0.1: Open EC2 security group port 3002

- [ ] **Step 1: Find the security group attached to the EC2 instance**

```bash
ssh atlas "curl -s http://169.254.169.254/latest/meta-data/security-groups"
```
Expected: a security group name (e.g., `atlas-prod-sg`).

- [ ] **Step 2: Add inbound rule via AWS CLI**

```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-XXXXXXXX \
  --protocol tcp --port 3002 --cidr 0.0.0.0/0 \
  --region ap-south-1
```
(Replace `sg-XXXXXXXX` with the actual security group ID. If `aws` CLI is not configured locally, do this in the AWS console.)

- [ ] **Step 3: Verify port reachable**

```bash
nc -vz 13.206.34.214 3002
```
Expected: at this stage, "Connection refused" — the port is open but nothing is listening yet. Good.

### Task 0.2: Set up `/home/ubuntu/atlas-frontend-v2/` deploy directory

- [ ] **Step 1: Clone the structure from existing atlas-frontend**

```bash
ssh atlas "
  mkdir -p /home/ubuntu/atlas-frontend-v2
  cp -R /home/ubuntu/atlas-frontend/package.json \
        /home/ubuntu/atlas-frontend/package-lock.json \
        /home/ubuntu/atlas-frontend/next.config.js \
        /home/ubuntu/atlas-frontend/tsconfig.json \
        /home/ubuntu/atlas-frontend/postcss.config.mjs \
        /home/ubuntu/atlas-frontend/eslint.config.mjs \
        /home/ubuntu/atlas-frontend/playwright.config.ts \
        /home/ubuntu/atlas-frontend/middleware.ts \
        /home/ubuntu/atlas-frontend/next-env.d.ts \
        /home/ubuntu/atlas-frontend-v2/
  ln -s /home/ubuntu/atlas-frontend-v2/frontend/src /home/ubuntu/atlas-frontend-v2/src 2>/dev/null || true
"
```

- [ ] **Step 2: Install dependencies**

```bash
ssh atlas "cd /home/ubuntu/atlas-frontend-v2 && npm install 2>&1 | tail -5"
```
Expected: "added N packages" and no errors.

- [ ] **Step 3: Copy current frontend source to bootstrap the build**

```bash
ssh atlas "
  mkdir -p /home/ubuntu/atlas-frontend-v2/frontend
  cp -R /home/ubuntu/atlas-frontend/frontend/src /home/ubuntu/atlas-frontend-v2/frontend/
  cp -R /home/ubuntu/atlas-frontend/frontend/public /home/ubuntu/atlas-frontend-v2/frontend/ 2>/dev/null || true
"
```

- [ ] **Step 4: Copy .env**

```bash
ssh atlas "cp /home/ubuntu/atlas-frontend/.env /home/ubuntu/atlas-frontend-v2/.env"
```

### Task 0.3: PM2 ecosystem entry on port 3002

- [ ] **Step 1: Write the ecosystem file**

```bash
ssh atlas "cat > /home/ubuntu/atlas-frontend-v2/ecosystem.config.js <<'EOF'
module.exports = {
  apps: [{
    name: 'atlas-frontend-v2',
    cwd:  '/home/ubuntu/atlas-frontend-v2',
    script: 'node_modules/.bin/next',
    args: 'start -p 3002',
    env: {
      NODE_ENV: 'production',
      PORT: '3002',
    },
    instances: 1,
    autorestart: true,
    max_memory_restart: '512M',
  }],
};
EOF
"
```

- [ ] **Step 2: Initial build (sanity check with current frontend code)**

```bash
ssh atlas "cd /home/ubuntu/atlas-frontend-v2 && npm run build 2>&1 | tail -10"
```
Expected: build succeeds.

- [ ] **Step 3: Start the PM2 process**

```bash
ssh atlas "cd /home/ubuntu/atlas-frontend-v2 && pm2 start ecosystem.config.js && pm2 save"
```

- [ ] **Step 4: Smoke test from local machine**

```bash
curl -s -o /dev/null -w 'HTTP %{http_code}\n' "http://13.206.34.214:3002/"
```
Expected: `HTTP 200` or `HTTP 307` (redirect to /login).

- [ ] **Step 5: Commit the deploy script on the consolidation branch**

Create `scripts/deploy_v2.sh`:

```bash
#!/usr/bin/env bash
# Deploys the current branch's frontend to /home/ubuntu/atlas-frontend-v2 on EC2.
# Used during signal-consolidation v2 demo build-out.
set -euo pipefail

BRANCH=$(git branch --show-current)
[ "$BRANCH" = "feat/atlas-consolidation" ] || {
  echo "Refusing to deploy from branch '$BRANCH' (expected feat/atlas-consolidation)"
  exit 1
}

echo "[deploy-v2] bundling frontend changes..."
tar -czf /tmp/atlas-frontend-v2.tgz frontend/src/

echo "[deploy-v2] shipping to EC2..."
scp /tmp/atlas-frontend-v2.tgz atlas:/tmp/

echo "[deploy-v2] extracting + building on EC2..."
ssh atlas '
  cd /home/ubuntu/atlas-frontend-v2 \
    && tar -xzf /tmp/atlas-frontend-v2.tgz \
    && npm run build 2>&1 | tail -5 \
    && pm2 restart atlas-frontend-v2
'

echo "[deploy-v2] done. Demo URL: http://13.206.34.214:3002/"
```

```bash
chmod +x scripts/deploy_v2.sh
git add scripts/deploy_v2.sh
git commit -m "feat(deploy): scripts/deploy_v2.sh — parallel frontend deploy to port 3002"
```

---

## Phase 1 — Bridge views (1 day CC)

Goal: a single SQL view per asset class re-derives every legacy column name from the new state engine, with no compute changes yet. Pages can begin reading from these views in Phase 6+ without backend changes.

### Task 1.1: Migration 080 — `atlas_stock_signal_unified` view

**Files:**
- Create: `migrations/versions/080_atlas_stock_signal_unified_view.py`
- Test: `tests/migrations/test_signal_unified_views.py`

- [ ] **Step 1: Write the failing test**

Create `tests/migrations/__init__.py` (empty if missing) and `tests/migrations/test_signal_unified_views.py`:

```python
"""Smoke tests for atlas_*_signal_unified views.

Verifies each view exists, returns rows, and exposes the legacy column
names every frontend query expects.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_stock_signal_unified_view_exists(engine: Engine) -> None:
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT
                instrument_id, date, engine_state, is_investable, rs_state,
                momentum_state, weinstein_gate_pass, within_state_rank,
                rs_rank_12m, dwell_days, urgency_score
            FROM atlas.atlas_stock_signal_unified
            LIMIT 1
        """)).first()
    assert row is not None, "view must return at least one row"
    assert row.engine_state in (
        "uninvestable", "stage_1", "stage_2a", "stage_2b", "stage_2c",
        "stage_3", "stage_4",
    )
    assert isinstance(row.is_investable, bool)
    assert row.rs_state in ("Leader", "Strong", "Average", "Weak", "Laggard")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/migrations/test_signal_unified_views.py::test_stock_signal_unified_view_exists -v
```
Expected: FAIL with `relation "atlas.atlas_stock_signal_unified" does not exist`.

- [ ] **Step 3: Write the migration**

Create `migrations/versions/080_atlas_stock_signal_unified_view.py`:

```python
"""atlas_stock_signal_unified view — derive legacy column names from state engine.

Revision ID: 080_stock_signal_unified
Revises: 079_atlas_component_validation
Create Date: 2026-05-18
"""
from alembic import op


revision = "080_stock_signal_unified"
down_revision = "079_atlas_component_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_stock_signal_unified AS
        SELECT
            s.instrument_id,
            s.date,
            s.state                                                  AS engine_state,
            s.prior_state,
            s.state_since_date,
            s.dwell_days,
            s.dwell_percentile::float8                               AS dwell_percentile,
            s.urgency_score,
            s.within_state_rank::float8                              AS within_state_rank,
            s.rs_rank_12m::float8                                    AS rs_rank_12m,
            NOT (s.state IN ('uninvestable','stage_4'))              AS is_investable,
            CASE
                WHEN s.rs_rank_12m >= 0.90 THEN 'Leader'
                WHEN s.rs_rank_12m >= 0.70 THEN 'Strong'
                WHEN s.rs_rank_12m >= 0.30 THEN 'Average'
                WHEN s.rs_rank_12m >= 0.10 THEN 'Weak'
                ELSE 'Laggard'
            END                                                       AS rs_state,
            CASE
                WHEN s.state IN ('stage_2a','stage_2b') THEN 'Accelerating'
                WHEN s.state = 'stage_2c'               THEN 'Improving'
                WHEN s.state = 'stage_3'                THEN 'Deteriorating'
                WHEN s.state = 'stage_4'                THEN 'Collapsing'
                ELSE 'Flat'
            END                                                       AS momentum_state,
            s.state IN ('stage_1','stage_2a','stage_2b','stage_2c')  AS weinstein_gate_pass,
            s.close_vs_sma_50::float8                                AS close_vs_sma_50,
            s.close_vs_sma_150::float8                               AS close_vs_sma_150,
            s.close_vs_sma_200::float8                               AS close_vs_sma_200,
            s.sma_200_slope::float8                                  AS sma_200_slope,
            s.volume_ratio_50d::float8                               AS volume_ratio_50d,
            s.distribution_days,
            s.classifier_version
        FROM atlas.atlas_stock_state_daily s
        WHERE s.classifier_version = 'v2.0-validated'
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS atlas.atlas_stock_signal_unified")
```

- [ ] **Step 4: Apply migration locally**

```bash
ATLAS_DB_URL=$ATLAS_DB_URL alembic upgrade head
```
Expected: `INFO  [alembic.runtime.migration] Running upgrade 079_atlas_component_validation -> 080_stock_signal_unified`.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/migrations/test_signal_unified_views.py::test_stock_signal_unified_view_exists -v
```
Expected: PASS.

- [ ] **Step 6: Apply migration on EC2 (.214)**

```bash
scp migrations/versions/080_atlas_stock_signal_unified_view.py atlas:/home/ubuntu/atlas-os-sl/migrations/versions/
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/alembic upgrade head"
```
Expected: same upgrade line.

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/080_atlas_stock_signal_unified_view.py tests/migrations/__init__.py tests/migrations/test_signal_unified_views.py
git commit -m "feat(signal-consolidation): migration 080 — atlas_stock_signal_unified view"
```

### Task 1.2: Smoke test view against live data (no code change)

**Files:** none (verification only)

- [ ] **Step 1: Verify row count parity with new engine**

```bash
ssh atlas "ATLAS_DB_URL='$ATLAS_DB_URL_EC2' psql -c \"
SELECT
  (SELECT COUNT(*) FROM atlas.atlas_stock_state_daily WHERE classifier_version='v2.0-validated') AS engine_rows,
  (SELECT COUNT(*) FROM atlas.atlas_stock_signal_unified) AS view_rows
\""
```
Expected: `engine_rows == view_rows`.

- [ ] **Step 2: Verify is_investable distribution**

```bash
ssh atlas "psql -c \"
SELECT is_investable, COUNT(*) FROM atlas.atlas_stock_signal_unified
WHERE date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
GROUP BY 1
\""
```
Expected: both true and false buckets non-zero.

- [ ] **Step 3: Verify rs_state distribution**

```bash
ssh atlas "psql -c \"
SELECT rs_state, COUNT(*) FROM atlas.atlas_stock_signal_unified
WHERE date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
GROUP BY 1 ORDER BY 1
\""
```
Expected: 5 buckets (Leader/Strong/Average/Weak/Laggard), none empty.

- [ ] **Step 4: Goal-post check**

```bash
atlas-lab goal-post --rank 1
```
Expected: `met:true`.

---

## Phase 2 — Aggregator modules (3 days CC)

Goal: pure-Python aggregators that take `atlas_stock_state_daily` as input and produce sector/fund/ETF aggregate state rows. No DB writes yet — Phase 3 wires persistence.

### Task 2.1: Aggregator base types

**Files:**
- Create: `atlas/intelligence/aggregations/__init__.py`
- Create: `atlas/intelligence/aggregations/base.py`
- Test: `tests/intelligence/aggregations/test_base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/aggregations/__init__.py` (empty) and `tests/intelligence/aggregations/test_base.py`:

```python
"""Tests for atlas/intelligence/aggregations/base.py."""
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)


def test_weighted_state_distribution_handles_simple_cap_weighting() -> None:
    df = pd.DataFrame({
        "instrument_id": ["a", "b", "c"],
        "state": ["stage_2a", "stage_2a", "stage_4"],
        "weight": [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
    })
    dist = weighted_state_distribution(df)
    assert dist["stage_2a"] == pytest.approx(0.8)
    assert dist["stage_4"] == pytest.approx(0.2)


def test_weighted_state_distribution_zero_weight_returns_empty() -> None:
    df = pd.DataFrame({
        "instrument_id": ["a"],
        "state": ["stage_2a"],
        "weight": [Decimal("0")],
    })
    dist = weighted_state_distribution(df)
    assert dist == {}


def test_aggregate_state_dominant_state() -> None:
    dist = {"stage_2a": 0.45, "stage_2b": 0.35, "stage_3": 0.20}
    agg = AggregateState.from_distribution(dist)
    assert agg.dominant_state == "stage_2a"
    assert agg.dominant_share == pytest.approx(0.45)
    assert agg.is_mixed is True  # no state > 0.50
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/intelligence/aggregations/test_base.py -v
```
Expected: FAIL with `ModuleNotFoundError: atlas.intelligence.aggregations.base`.

- [ ] **Step 3: Create the package marker**

Create `atlas/intelligence/aggregations/__init__.py`:

```python
"""Bottom-up aggregations from atlas_stock_state_daily to sector/fund/ETF states."""
```

- [ ] **Step 4: Implement base.py**

Create `atlas/intelligence/aggregations/base.py`:

```python
"""Shared types and helpers for bottom-up state aggregations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

# Threshold above which we call one state "dominant"; below = mixed.
DOMINANT_THRESHOLD = 0.50

# Order matters for tie-breaking — earlier states are more bullish.
STATE_ORDER = (
    "stage_2a", "stage_2b", "stage_2c", "stage_1",
    "stage_3", "stage_4", "uninvestable",
)


def weighted_state_distribution(df: pd.DataFrame) -> dict[str, float]:
    """Compute weighted share of each state.

    Required columns: ``state`` (str), ``weight`` (Decimal or float).
    Weights are normalized to sum to 1; states with zero total weight
    return an empty dict.
    """
    if df.empty:
        return {}
    df = df.copy()
    df["weight"] = df["weight"].astype(float)
    total = df["weight"].sum()
    if total <= 0:
        return {}
    grouped = df.groupby("state")["weight"].sum() / total
    return grouped.to_dict()


@dataclass(frozen=True)
class AggregateState:
    """Result of aggregating constituent stock states."""

    dominant_state: str
    dominant_share: float
    distribution: dict[str, float]
    n_constituents: int

    @property
    def is_mixed(self) -> bool:
        return self.dominant_share < DOMINANT_THRESHOLD

    @classmethod
    def from_distribution(cls, distribution: dict[str, float]) -> "AggregateState":
        if not distribution:
            return cls("uninvestable", 0.0, {}, 0)
        # Pick the state with max share; break ties by STATE_ORDER index.
        dominant = max(
            distribution.items(),
            key=lambda kv: (kv[1], -STATE_ORDER.index(kv[0]) if kv[0] in STATE_ORDER else -99),
        )
        return cls(
            dominant_state=dominant[0],
            dominant_share=dominant[1],
            distribution=distribution,
            n_constituents=len(distribution),
        )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/intelligence/aggregations/test_base.py -v
```
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add atlas/intelligence/aggregations/__init__.py atlas/intelligence/aggregations/base.py tests/intelligence/aggregations/__init__.py tests/intelligence/aggregations/test_base.py
git commit -m "feat(aggregations): base types — AggregateState + weighted_state_distribution"
```

### Task 2.2: Sector aggregator

**Files:**
- Create: `atlas/intelligence/aggregations/sector.py`
- Test: `tests/intelligence/aggregations/test_sector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/aggregations/test_sector.py`:

```python
"""Tests for atlas/intelligence/aggregations/sector.py."""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.sector import aggregate_sector_states


def _stock_panel() -> pd.DataFrame:
    return pd.DataFrame([
        # Banking sector — mostly stage 2
        {"instrument_id": "b1", "sector": "Banking",  "date": date(2024, 12, 31),
         "state": "stage_2a", "within_state_rank": 0.85, "rs_rank_12m": 0.80,
         "market_cap": Decimal("1000")},
        {"instrument_id": "b2", "sector": "Banking",  "date": date(2024, 12, 31),
         "state": "stage_2b", "within_state_rank": 0.70, "rs_rank_12m": 0.75,
         "market_cap": Decimal("500")},
        {"instrument_id": "b3", "sector": "Banking",  "date": date(2024, 12, 31),
         "state": "stage_3",  "within_state_rank": 0.40, "rs_rank_12m": 0.40,
         "market_cap": Decimal("200")},
        # IT sector — mostly stage 4
        {"instrument_id": "i1", "sector": "IT",       "date": date(2024, 12, 31),
         "state": "stage_4",  "within_state_rank": None, "rs_rank_12m": 0.20,
         "market_cap": Decimal("800")},
        {"instrument_id": "i2", "sector": "IT",       "date": date(2024, 12, 31),
         "state": "stage_4",  "within_state_rank": None, "rs_rank_12m": 0.15,
         "market_cap": Decimal("600")},
    ])


def test_aggregate_sector_states_yields_one_row_per_sector_per_date() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    assert len(out) == 2
    assert set(out["sector"].tolist()) == {"Banking", "IT"}


def test_aggregate_sector_states_banking_dominant_state_is_stage_2() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    banking = out[out["sector"] == "Banking"].iloc[0]
    # Banking by market-cap weight: 1000+500=1500 stage_2 vs 200 stage_3.
    assert banking["dominant_state"] in ("stage_2a", "stage_2b")
    assert banking["dominant_share"] == pytest.approx(1500 / 1700, rel=1e-3)


def test_aggregate_sector_states_it_dominant_state_is_stage_4() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    it = out[out["sector"] == "IT"].iloc[0]
    assert it["dominant_state"] == "stage_4"
    assert it["dominant_share"] == pytest.approx(1.0)


def test_aggregate_sector_states_mean_within_state_rank_excludes_nulls() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    banking = out[out["sector"] == "Banking"].iloc[0]
    # Banking constituents within_state_rank: 0.85, 0.70, 0.40 → mean 0.65
    assert banking["mean_within_state_rank"] == pytest.approx(0.65)
    it = out[out["sector"] == "IT"].iloc[0]
    assert it["mean_within_state_rank"] is None or pd.isna(it["mean_within_state_rank"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/intelligence/aggregations/test_sector.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement sector.py**

Create `atlas/intelligence/aggregations/sector.py`:

```python
"""Bottom-up sector state aggregator.

Reads ``atlas_stock_state_daily`` joined to ``atlas_universe_stocks``
(for sector + market_cap weights), produces one row per (sector, date)
with dominant state, distribution, breadth metrics.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)


_PANEL_SQL = text("""
    SELECT
        s.instrument_id::text       AS instrument_id,
        u.sector                    AS sector,
        s.date                      AS date,
        s.state                     AS state,
        s.within_state_rank::float8 AS within_state_rank,
        s.rs_rank_12m::float8       AS rs_rank_12m,
        u.market_cap_inr            AS market_cap
    FROM atlas.atlas_stock_state_daily s
    JOIN atlas.atlas_universe_stocks u USING (instrument_id)
    WHERE s.classifier_version = 'v2.0-validated'
      AND (:as_of_date IS NULL OR s.date = :as_of_date::date)
      AND u.sector IS NOT NULL
""")


def load_stock_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a stock-day panel suitable for aggregation."""
    with engine.connect() as c:
        df = pd.read_sql(_PANEL_SQL, c, params={"as_of_date": as_of_date})
    return df


def aggregate_sector_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate stock panel into sector-day rows.

    Returns a DataFrame with columns: sector, date, dominant_state,
    dominant_share, n_constituents, mean_within_state_rank,
    pct_stage_2 (sum of stage_2a/2b/2c), pct_stage_3, pct_stage_4,
    pct_stage_1, pct_uninvestable.
    """
    if panel.empty:
        return pd.DataFrame(columns=[
            "sector", "date", "dominant_state", "dominant_share",
            "n_constituents", "mean_within_state_rank",
            "pct_stage_2", "pct_stage_3", "pct_stage_4",
            "pct_stage_1", "pct_uninvestable",
        ])

    rows: list[dict[str, object]] = []
    for (sector, dt), group in panel.groupby(["sector", "date"]):
        weighted = group.rename(columns={"market_cap": "weight"})
        dist = weighted_state_distribution(weighted[["state", "weight"]])
        agg = AggregateState.from_distribution(dist)
        wsr = group["within_state_rank"].dropna()
        rows.append({
            "sector": sector,
            "date": dt,
            "dominant_state": agg.dominant_state,
            "dominant_share": agg.dominant_share,
            "n_constituents": len(group),
            "mean_within_state_rank": (
                float(wsr.mean()) if not wsr.empty else None
            ),
            "pct_stage_2": (
                dist.get("stage_2a", 0.0)
                + dist.get("stage_2b", 0.0)
                + dist.get("stage_2c", 0.0)
            ),
            "pct_stage_3": dist.get("stage_3", 0.0),
            "pct_stage_4": dist.get("stage_4", 0.0),
            "pct_stage_1": dist.get("stage_1", 0.0),
            "pct_uninvestable": dist.get("uninvestable", 0.0),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/intelligence/aggregations/test_sector.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/aggregations/sector.py tests/intelligence/aggregations/test_sector.py
git commit -m "feat(aggregations): bottom-up sector state aggregator"
```

### Task 2.3: Fund aggregator (composition + holdings, nav_state passthrough)

**Files:**
- Create: `atlas/intelligence/aggregations/fund.py`
- Test: `tests/intelligence/aggregations/test_fund.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/aggregations/test_fund.py`:

```python
"""Tests for atlas/intelligence/aggregations/fund.py."""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.fund import (
    aggregate_fund_composition,
    derive_fund_recommendation,
)


def _holdings_panel() -> pd.DataFrame:
    return pd.DataFrame([
        {"mstar_id": "F1", "date": date(2024, 12, 31), "instrument_id": "a",
         "weight_pct": Decimal("40"), "state": "stage_2a", "within_state_rank": 0.80},
        {"mstar_id": "F1", "date": date(2024, 12, 31), "instrument_id": "b",
         "weight_pct": Decimal("35"), "state": "stage_2b", "within_state_rank": 0.70},
        {"mstar_id": "F1", "date": date(2024, 12, 31), "instrument_id": "c",
         "weight_pct": Decimal("25"), "state": "stage_4",  "within_state_rank": None},
        {"mstar_id": "F2", "date": date(2024, 12, 31), "instrument_id": "d",
         "weight_pct": Decimal("60"), "state": "stage_4",  "within_state_rank": None},
        {"mstar_id": "F2", "date": date(2024, 12, 31), "instrument_id": "e",
         "weight_pct": Decimal("40"), "state": "stage_3",  "within_state_rank": 0.30},
    ])


def test_aggregate_fund_composition_yields_one_row_per_fund() -> None:
    out = aggregate_fund_composition(_holdings_panel())
    assert len(out) == 2
    assert set(out["mstar_id"]) == {"F1", "F2"}


def test_aggregate_fund_composition_f1_aligned_to_stage_2() -> None:
    out = aggregate_fund_composition(_holdings_panel())
    f1 = out[out["mstar_id"] == "F1"].iloc[0]
    # 40% stage_2a + 35% stage_2b = 75% in stage 2 → composition_state='Aligned'
    assert f1["composition_state"] == "Aligned"
    assert f1["pct_holdings_stage_2"] == pytest.approx(0.75)


def test_aggregate_fund_composition_f2_deteriorating() -> None:
    out = aggregate_fund_composition(_holdings_panel())
    f2 = out[out["mstar_id"] == "F2"].iloc[0]
    # 100% stage_3/4 → composition_state='Deteriorating'
    assert f2["composition_state"] == "Deteriorating"


def test_derive_fund_recommendation_aligned_strong_holdings_recommends() -> None:
    rec = derive_fund_recommendation(
        nav_state="Leader NAV",
        composition_state="Aligned",
        holdings_state="Strong-Holdings",
    )
    assert rec == "Recommended"


def test_derive_fund_recommendation_deteriorating_recommends_avoid() -> None:
    rec = derive_fund_recommendation(
        nav_state="Weak NAV",
        composition_state="Deteriorating",
        holdings_state="Weak-Holdings",
    )
    assert rec == "Avoid"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/intelligence/aggregations/test_fund.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement fund.py**

Create `atlas/intelligence/aggregations/fund.py`:

```python
"""Bottom-up fund composition + holdings aggregator.

Composition: % of fund AUM in each Weinstein state across constituent holdings.
Holdings: mean within_state_rank across holdings as a quality proxy.
Recommendation: derived from (nav_state, composition_state, holdings_state).

nav_state remains a fund-internal NAV-vs-category computation produced by
``atlas/compute/lens_nav.py``; this module only consumes it.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Thresholds for composition_state classification.
ALIGNED_THRESHOLD = 0.60        # ≥ 60% of holdings in stage 2 → Aligned
DETERIORATING_THRESHOLD = 0.40  # ≥ 40% in stage 3/4 → Deteriorating

# Thresholds for holdings_state classification.
STRONG_HOLDINGS_THRESHOLD = 0.60  # mean within_state_rank ≥ 0.60
WEAK_HOLDINGS_THRESHOLD = 0.30    # mean within_state_rank ≤ 0.30


_HOLDINGS_SQL = text("""
    SELECT
        h.mstar_id::text             AS mstar_id,
        h.as_of_date                 AS date,
        h.instrument_id::text        AS instrument_id,
        h.weight_pct                 AS weight_pct,
        s.state                      AS state,
        s.within_state_rank::float8  AS within_state_rank
    FROM atlas.atlas_fund_holdings h
    JOIN atlas.atlas_stock_state_daily s
      ON s.instrument_id = h.instrument_id
     AND s.date          = h.as_of_date
     AND s.classifier_version = 'v2.0-validated'
    WHERE (:as_of_date IS NULL OR h.as_of_date = :as_of_date::date)
""")


def load_fund_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a fund-holding-day panel suitable for composition aggregation."""
    with engine.connect() as c:
        return pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})


def aggregate_fund_composition(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fund holdings into composition + holdings states."""
    if panel.empty:
        return pd.DataFrame(columns=[
            "mstar_id", "date", "composition_state", "holdings_state",
            "pct_holdings_stage_2", "pct_holdings_stage_3", "pct_holdings_stage_4",
            "mean_within_state_rank", "n_holdings",
        ])

    rows: list[dict[str, object]] = []
    panel = panel.copy()
    panel["weight_pct"] = panel["weight_pct"].astype(float) / 100.0

    for (mstar_id, dt), group in panel.groupby(["mstar_id", "date"]):
        total = group["weight_pct"].sum()
        norm = group["weight_pct"] / total if total > 0 else group["weight_pct"]
        pct = group["state"].groupby(group["state"]).apply(
            lambda _s: norm[group["state"] == _s.iloc[0]].sum()
        ).to_dict()
        pct_stage_2 = sum(pct.get(s, 0.0) for s in ("stage_2a", "stage_2b", "stage_2c"))
        pct_stage_3 = pct.get("stage_3", 0.0)
        pct_stage_4 = pct.get("stage_4", 0.0)
        wsr = group["within_state_rank"].dropna()
        mean_wsr = float(wsr.mean()) if not wsr.empty else None

        if pct_stage_2 >= ALIGNED_THRESHOLD:
            comp = "Aligned"
        elif (pct_stage_3 + pct_stage_4) >= DETERIORATING_THRESHOLD:
            comp = "Deteriorating"
        else:
            comp = "Mixed"

        if mean_wsr is None:
            holdings = "Unknown"
        elif mean_wsr >= STRONG_HOLDINGS_THRESHOLD:
            holdings = "Strong-Holdings"
        elif mean_wsr <= WEAK_HOLDINGS_THRESHOLD:
            holdings = "Weak-Holdings"
        else:
            holdings = "Mixed-Holdings"

        rows.append({
            "mstar_id": mstar_id,
            "date": dt,
            "composition_state": comp,
            "holdings_state": holdings,
            "pct_holdings_stage_2": pct_stage_2,
            "pct_holdings_stage_3": pct_stage_3,
            "pct_holdings_stage_4": pct_stage_4,
            "mean_within_state_rank": mean_wsr,
            "n_holdings": int(len(group)),
        })
    return pd.DataFrame(rows)


# Recommendation lookup table — (nav, composition, holdings) → recommendation.
# Conservative-first: any "Avoid" condition dominates.
def derive_fund_recommendation(
    nav_state: str | None,
    composition_state: str,
    holdings_state: str,
) -> str:
    """Map the 3-tuple to Recommended / Hold / Avoid."""
    if nav_state == "DISLOCATION_SUSPENDED":
        return "Avoid"
    if composition_state == "Deteriorating" or holdings_state == "Weak-Holdings":
        return "Avoid"
    if (
        composition_state == "Aligned"
        and holdings_state == "Strong-Holdings"
        and (nav_state in ("Leader NAV", "Strong NAV", None))
    ):
        return "Recommended"
    return "Hold"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/intelligence/aggregations/test_fund.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/aggregations/fund.py tests/intelligence/aggregations/test_fund.py
git commit -m "feat(aggregations): bottom-up fund composition + holdings + recommendation"
```

### Task 2.4: ETF aggregator

**Files:**
- Create: `atlas/intelligence/aggregations/etf.py`
- Test: `tests/intelligence/aggregations/test_etf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/aggregations/test_etf.py`:

```python
"""Tests for atlas/intelligence/aggregations/etf.py."""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.etf import aggregate_etf_states


def _etf_holdings() -> pd.DataFrame:
    return pd.DataFrame([
        {"etf_ticker": "NIFTYBEES", "date": date(2024, 12, 31),
         "instrument_id": "a", "weight_pct": Decimal("60"),
         "state": "stage_2a", "rs_rank_12m": 0.80},
        {"etf_ticker": "NIFTYBEES", "date": date(2024, 12, 31),
         "instrument_id": "b", "weight_pct": Decimal("40"),
         "state": "stage_2b", "rs_rank_12m": 0.75},
        {"etf_ticker": "BANKBEES",  "date": date(2024, 12, 31),
         "instrument_id": "c", "weight_pct": Decimal("100"),
         "state": "stage_3",  "rs_rank_12m": 0.40},
    ])


def test_aggregate_etf_states_one_row_per_etf() -> None:
    out = aggregate_etf_states(_etf_holdings())
    assert len(out) == 2


def test_aggregate_etf_states_niftybees_stage_2_dominant() -> None:
    out = aggregate_etf_states(_etf_holdings())
    n = out[out["etf_ticker"] == "NIFTYBEES"].iloc[0]
    assert n["dominant_state"] in ("stage_2a", "stage_2b")
    assert n["mean_rs_rank_12m"] == pytest.approx(0.60 * 0.80 + 0.40 * 0.75)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/intelligence/aggregations/test_etf.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement etf.py**

Create `atlas/intelligence/aggregations/etf.py`:

```python
"""Bottom-up ETF state aggregator.

For each (etf_ticker, date), aggregates constituent stock states
weighted by holding weight_pct.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)


_HOLDINGS_SQL = text("""
    SELECT
        h.etf_ticker             AS etf_ticker,
        h.as_of_date             AS date,
        h.instrument_id::text    AS instrument_id,
        h.weight_pct             AS weight_pct,
        s.state                  AS state,
        s.rs_rank_12m::float8    AS rs_rank_12m
    FROM atlas.atlas_etf_holdings h
    JOIN atlas.atlas_stock_state_daily s
      ON s.instrument_id = h.instrument_id
     AND s.date          = h.as_of_date
     AND s.classifier_version = 'v2.0-validated'
    WHERE (:as_of_date IS NULL OR h.as_of_date = :as_of_date::date)
""")


def load_etf_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load an ETF-holding-day panel suitable for aggregation."""
    with engine.connect() as c:
        return pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})


def aggregate_etf_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ETF holdings into ETF-day state rows."""
    if panel.empty:
        return pd.DataFrame(columns=[
            "etf_ticker", "date", "dominant_state", "dominant_share",
            "n_holdings", "mean_rs_rank_12m",
            "pct_stage_2", "pct_stage_3", "pct_stage_4",
        ])

    panel = panel.copy()
    panel["weight_pct"] = panel["weight_pct"].astype(float)

    rows: list[dict[str, object]] = []
    for (ticker, dt), group in panel.groupby(["etf_ticker", "date"]):
        weighted = group.rename(columns={"weight_pct": "weight"})
        dist = weighted_state_distribution(weighted[["state", "weight"]])
        agg = AggregateState.from_distribution(dist)
        total_w = group["weight_pct"].sum()
        mean_rs = (
            (group["weight_pct"] * group["rs_rank_12m"]).sum() / total_w
            if total_w > 0 else None
        )
        rows.append({
            "etf_ticker": ticker,
            "date": dt,
            "dominant_state": agg.dominant_state,
            "dominant_share": agg.dominant_share,
            "n_holdings": int(len(group)),
            "mean_rs_rank_12m": (
                float(mean_rs) if mean_rs is not None else None
            ),
            "pct_stage_2": (
                dist.get("stage_2a", 0.0)
                + dist.get("stage_2b", 0.0)
                + dist.get("stage_2c", 0.0)
            ),
            "pct_stage_3": dist.get("stage_3", 0.0),
            "pct_stage_4": dist.get("stage_4", 0.0),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/intelligence/aggregations/test_etf.py -v
```
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/aggregations/etf.py tests/intelligence/aggregations/test_etf.py
git commit -m "feat(aggregations): bottom-up ETF state aggregator"
```

---

## Phase 3 — Aggregation persistence + tables (2 days CC)

Goal: three new tables receive the aggregator output. Existing legacy aggregate tables remain untouched (they continue to be written by the legacy compute paths until Phase 8 cuts them over).

### Task 3.1: Migration 084 — `atlas_sector_state_v2` table

**Files:**
- Create: `migrations/versions/084_atlas_sector_state_v2_table.py`
- Test: `tests/migrations/test_signal_unified_views.py` (extend)

- [ ] **Step 1: Add test for new table**

Append to `tests/migrations/test_signal_unified_views.py`:

```python
def test_atlas_sector_state_v2_table_exists(engine: Engine) -> None:
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'atlas'
              AND table_name   = 'atlas_sector_state_v2'
        """)).fetchall()
    cols = {r.column_name for r in row}
    expected = {
        "sector", "date", "dominant_state", "dominant_share",
        "n_constituents", "mean_within_state_rank",
        "pct_stage_2", "pct_stage_3", "pct_stage_4",
        "pct_stage_1", "pct_uninvestable", "computed_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/migrations/test_signal_unified_views.py::test_atlas_sector_state_v2_table_exists -v
```
Expected: FAIL — table missing.

- [ ] **Step 3: Write migration**

Create `migrations/versions/084_atlas_sector_state_v2_table.py`:

```python
"""atlas_sector_state_v2 table — bottom-up sector aggregate state.

Revision ID: 084_sector_state_v2
Revises: 083_atlas_etf_signal_unified_view
Create Date: 2026-05-18
"""
import sqlalchemy as sa
from alembic import op


revision = "084_sector_state_v2"
down_revision = "083_atlas_etf_signal_unified_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_sector_state_v2",
        sa.Column("sector", sa.String(64), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("dominant_state", sa.String(20), nullable=False),
        sa.Column("dominant_share", sa.Numeric(6, 4), nullable=False),
        sa.Column("n_constituents", sa.Integer, nullable=False),
        sa.Column("mean_within_state_rank", sa.Numeric(6, 4), nullable=True),
        sa.Column("pct_stage_2", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_3", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_4", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_1", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_uninvestable", sa.Numeric(6, 4), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  nullable=False),
        sa.PrimaryKeyConstraint("sector", "date"),
        sa.CheckConstraint(
            "dominant_state IN ('uninvestable','stage_1','stage_2a','stage_2b',"
            "'stage_2c','stage_3','stage_4')",
            name="ck_sector_state_v2_dominant_state",
        ),
        schema="atlas",
    )
    op.create_index(
        "ix_sector_state_v2_date",
        "atlas_sector_state_v2",
        ["date"],
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_index("ix_sector_state_v2_date", "atlas_sector_state_v2", schema="atlas")
    op.drop_table("atlas_sector_state_v2", schema="atlas")
```

(Note: this task assumes migrations 081, 082, 083 — the three remaining `*_signal_unified` views — have already been created. They are mechanical copies of 080 adapted for sector / fund / ETF and not separately specified here. See Task 1.1 for the pattern.)

- [ ] **Step 4: Write migrations 081, 082, 083 (sector / fund / etf signal_unified views)**

Each follows the 080 pattern but reads from the corresponding aggregate table. Until those v2 tables exist (after Phase 3), these views can be defined to read from the legacy `atlas_*_states_daily` for now — they get rewritten in Phase 8.

For migration `081_atlas_sector_signal_unified_view.py`, the view body:

```sql
CREATE OR REPLACE VIEW atlas.atlas_sector_signal_unified AS
SELECT
    s.sector,
    s.date,
    s.dominant_state                                              AS engine_state,
    s.dominant_share::float8                                      AS dominant_share,
    s.n_constituents,
    s.mean_within_state_rank::float8                              AS mean_within_state_rank,
    s.pct_stage_2::float8                                         AS pct_stage_2,
    s.pct_stage_3::float8                                         AS pct_stage_3,
    s.pct_stage_4::float8                                         AS pct_stage_4,
    CASE
        WHEN s.pct_stage_2 >= 0.50 THEN 'Overweight'
        WHEN s.pct_stage_4 >= 0.50 THEN 'Avoid'
        WHEN s.pct_stage_3 + s.pct_stage_4 >= 0.50 THEN 'Underweight'
        ELSE 'Neutral'
    END                                                           AS sector_state
FROM atlas.atlas_sector_state_v2 s
```

For `082_atlas_fund_signal_unified_view.py`:

```sql
CREATE OR REPLACE VIEW atlas.atlas_fund_signal_unified AS
SELECT
    fv.mstar_id,
    fv.date,
    fv.composition_state,
    fv.holdings_state,
    fv.pct_holdings_stage_2::float8 AS pct_holdings_stage_2,
    fv.pct_holdings_stage_3::float8 AS pct_holdings_stage_3,
    fv.pct_holdings_stage_4::float8 AS pct_holdings_stage_4,
    fv.mean_within_state_rank::float8 AS mean_within_state_rank,
    fv.n_holdings,
    nav.nav_state,
    nav.nav_state_as_of,
    CASE
        WHEN nav.nav_state = 'DISLOCATION_SUSPENDED' THEN 'Avoid'
        WHEN fv.composition_state = 'Deteriorating'
             OR fv.holdings_state  = 'Weak-Holdings'  THEN 'Avoid'
        WHEN fv.composition_state = 'Aligned'
             AND fv.holdings_state = 'Strong-Holdings'
             AND nav.nav_state IN ('Leader NAV','Strong NAV') THEN 'Recommended'
        ELSE 'Hold'
    END AS recommendation
FROM atlas.atlas_fund_state_v2 fv
LEFT JOIN atlas.atlas_fund_states_daily nav
  ON nav.mstar_id = fv.mstar_id
 AND nav.date     = fv.date
```

For `083_atlas_etf_signal_unified_view.py`:

```sql
CREATE OR REPLACE VIEW atlas.atlas_etf_signal_unified AS
SELECT
    e.etf_ticker,
    e.date,
    e.dominant_state                AS engine_state,
    e.dominant_share::float8        AS dominant_share,
    e.n_holdings,
    e.mean_rs_rank_12m::float8      AS mean_rs_rank_12m,
    e.pct_stage_2::float8           AS pct_stage_2,
    e.pct_stage_3::float8           AS pct_stage_3,
    e.pct_stage_4::float8           AS pct_stage_4
FROM atlas.atlas_etf_state_v2 e
```

These three migrations are mechanical and follow the 080 pattern (revision id, downgrade dropping the view).

- [ ] **Step 5: Apply 081–084 locally**

```bash
alembic upgrade head
```
Expected: 4 upgrade lines.

- [ ] **Step 6: Run tests**

```bash
pytest tests/migrations/ -v
```
Expected: 2 PASS (1 from Task 1.1, 1 from this task). The 081/082/083 views currently read from tables that don't exist yet (`atlas_sector_state_v2`, `atlas_fund_state_v2`, `atlas_etf_state_v2`). Migration 084 creates `atlas_sector_state_v2`; equivalent migrations 085 and 086 will follow.

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/081_atlas_sector_signal_unified_view.py \
        migrations/versions/082_atlas_fund_signal_unified_view.py \
        migrations/versions/083_atlas_etf_signal_unified_view.py \
        migrations/versions/084_atlas_sector_state_v2_table.py \
        tests/migrations/test_signal_unified_views.py
git commit -m "feat(signal-consolidation): aggregate state tables + unified views (081–084)"
```

### Task 3.2: Migrations 085 + 086 — `atlas_fund_state_v2` and `atlas_etf_state_v2`

**Files:**
- Create: `migrations/versions/085_atlas_fund_state_v2_table.py`
- Create: `migrations/versions/086_atlas_etf_state_v2_table.py`
- Modify: `tests/migrations/test_signal_unified_views.py`

- [ ] **Step 1: Extend the test file**

Append:

```python
def test_atlas_fund_state_v2_table_exists(engine: Engine) -> None:
    with engine.connect() as c:
        cols = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='atlas' AND table_name='atlas_fund_state_v2'
        """)).fetchall()
    names = {r.column_name for r in cols}
    expected = {
        "mstar_id", "date", "composition_state", "holdings_state",
        "pct_holdings_stage_2", "pct_holdings_stage_3", "pct_holdings_stage_4",
        "mean_within_state_rank", "n_holdings", "computed_at",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_atlas_etf_state_v2_table_exists(engine: Engine) -> None:
    with engine.connect() as c:
        cols = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='atlas' AND table_name='atlas_etf_state_v2'
        """)).fetchall()
    names = {r.column_name for r in cols}
    expected = {
        "etf_ticker", "date", "dominant_state", "dominant_share",
        "n_holdings", "mean_rs_rank_12m",
        "pct_stage_2", "pct_stage_3", "pct_stage_4", "computed_at",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
```

- [ ] **Step 2: Run tests — expect fail**

```bash
pytest tests/migrations/test_signal_unified_views.py -k "fund_state_v2 or etf_state_v2" -v
```

- [ ] **Step 3: Write migration 085**

Create `migrations/versions/085_atlas_fund_state_v2_table.py`:

```python
"""atlas_fund_state_v2 table — bottom-up fund composition + holdings aggregate.

Revision ID: 085_fund_state_v2
Revises: 084_sector_state_v2
Create Date: 2026-05-18
"""
import sqlalchemy as sa
from alembic import op


revision = "085_fund_state_v2"
down_revision = "084_sector_state_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_fund_state_v2",
        sa.Column("mstar_id", sa.String(32), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("composition_state", sa.String(24), nullable=False),
        sa.Column("holdings_state", sa.String(24), nullable=False),
        sa.Column("pct_holdings_stage_2", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_holdings_stage_3", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_holdings_stage_4", sa.Numeric(6, 4), nullable=False),
        sa.Column("mean_within_state_rank", sa.Numeric(6, 4), nullable=True),
        sa.Column("n_holdings", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  nullable=False),
        sa.PrimaryKeyConstraint("mstar_id", "date"),
        sa.CheckConstraint(
            "composition_state IN ('Aligned','Deteriorating','Mixed')",
            name="ck_fund_state_v2_composition",
        ),
        sa.CheckConstraint(
            "holdings_state IN ('Strong-Holdings','Weak-Holdings','Mixed-Holdings','Unknown')",
            name="ck_fund_state_v2_holdings",
        ),
        schema="atlas",
    )
    op.create_index(
        "ix_fund_state_v2_date",
        "atlas_fund_state_v2",
        ["date"],
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_index("ix_fund_state_v2_date", "atlas_fund_state_v2", schema="atlas")
    op.drop_table("atlas_fund_state_v2", schema="atlas")
```

- [ ] **Step 4: Write migration 086**

Create `migrations/versions/086_atlas_etf_state_v2_table.py`:

```python
"""atlas_etf_state_v2 table — bottom-up ETF state aggregate.

Revision ID: 086_etf_state_v2
Revises: 085_fund_state_v2
Create Date: 2026-05-18
"""
import sqlalchemy as sa
from alembic import op


revision = "086_etf_state_v2"
down_revision = "085_fund_state_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_etf_state_v2",
        sa.Column("etf_ticker", sa.String(32), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("dominant_state", sa.String(20), nullable=False),
        sa.Column("dominant_share", sa.Numeric(6, 4), nullable=False),
        sa.Column("n_holdings", sa.Integer, nullable=False),
        sa.Column("mean_rs_rank_12m", sa.Numeric(6, 4), nullable=True),
        sa.Column("pct_stage_2", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_3", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_4", sa.Numeric(6, 4), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  nullable=False),
        sa.PrimaryKeyConstraint("etf_ticker", "date"),
        sa.CheckConstraint(
            "dominant_state IN ('uninvestable','stage_1','stage_2a','stage_2b',"
            "'stage_2c','stage_3','stage_4')",
            name="ck_etf_state_v2_dominant_state",
        ),
        schema="atlas",
    )
    op.create_index(
        "ix_etf_state_v2_date",
        "atlas_etf_state_v2",
        ["date"],
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_index("ix_etf_state_v2_date", "atlas_etf_state_v2", schema="atlas")
    op.drop_table("atlas_etf_state_v2", schema="atlas")
```

- [ ] **Step 5: Apply locally + EC2**

```bash
alembic upgrade head
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/alembic upgrade head"
```

- [ ] **Step 6: Run tests — expect pass**

```bash
pytest tests/migrations/test_signal_unified_views.py -v
```

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/085_atlas_fund_state_v2_table.py \
        migrations/versions/086_atlas_etf_state_v2_table.py \
        tests/migrations/test_signal_unified_views.py
git commit -m "feat(signal-consolidation): atlas_fund_state_v2 + atlas_etf_state_v2 tables"
```

### Task 3.3: Persistence writer

**Files:**
- Create: `atlas/intelligence/aggregations/persistence.py`
- Test: `tests/intelligence/aggregations/test_persistence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/aggregations/test_persistence.py`:

```python
"""Tests for atlas/intelligence/aggregations/persistence.py."""
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.intelligence.aggregations.persistence import (
    persist_sector_state_v2,
    persist_fund_state_v2,
    persist_etf_state_v2,
)


def test_persist_sector_state_v2_inserts_then_upserts(test_engine) -> None:
    df = pd.DataFrame([{
        "sector": "Banking", "date": date(2024, 12, 31),
        "dominant_state": "stage_2a", "dominant_share": 0.7,
        "n_constituents": 10, "mean_within_state_rank": 0.65,
        "pct_stage_2": 0.7, "pct_stage_3": 0.2, "pct_stage_4": 0.1,
        "pct_stage_1": 0.0, "pct_uninvestable": 0.0,
    }])
    n1 = persist_sector_state_v2(test_engine, df)
    assert n1 == 1
    # Re-run with new dominant_state — must upsert, not duplicate.
    df.loc[0, "dominant_state"] = "stage_2b"
    n2 = persist_sector_state_v2(test_engine, df)
    assert n2 == 1
    with test_engine.connect() as c:
        rows = c.execute(text(
            "SELECT dominant_state FROM atlas.atlas_sector_state_v2 "
            "WHERE sector='Banking' AND date='2024-12-31'"
        )).fetchall()
    assert len(rows) == 1
    assert rows[0].dominant_state == "stage_2b"
```

(test_engine fixture is the standard fixture providing a clean Postgres engine; see `conftest.py`.)

- [ ] **Step 2: Run test — expect fail (module missing)**

```bash
pytest tests/intelligence/aggregations/test_persistence.py -v
```

- [ ] **Step 3: Implement persistence.py**

Create `atlas/intelligence/aggregations/persistence.py`:

```python
"""UPSERT writers for atlas_*_state_v2 aggregate tables."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


_SECTOR_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_sector_state_v2 (
        sector, date, dominant_state, dominant_share, n_constituents,
        mean_within_state_rank, pct_stage_2, pct_stage_3, pct_stage_4,
        pct_stage_1, pct_uninvestable
    ) VALUES (
        :sector, :date, :dominant_state, :dominant_share, :n_constituents,
        :mean_within_state_rank, :pct_stage_2, :pct_stage_3, :pct_stage_4,
        :pct_stage_1, :pct_uninvestable
    )
    ON CONFLICT (sector, date) DO UPDATE SET
        dominant_state         = EXCLUDED.dominant_state,
        dominant_share         = EXCLUDED.dominant_share,
        n_constituents         = EXCLUDED.n_constituents,
        mean_within_state_rank = EXCLUDED.mean_within_state_rank,
        pct_stage_2            = EXCLUDED.pct_stage_2,
        pct_stage_3            = EXCLUDED.pct_stage_3,
        pct_stage_4            = EXCLUDED.pct_stage_4,
        pct_stage_1            = EXCLUDED.pct_stage_1,
        pct_uninvestable       = EXCLUDED.pct_uninvestable,
        computed_at            = CURRENT_TIMESTAMP
""")


def persist_sector_state_v2(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a DataFrame of sector aggregate rows. Returns the row count."""
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    with engine.begin() as c:
        c.execute(_SECTOR_UPSERT_SQL, records)
    return len(records)


_FUND_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_fund_state_v2 (
        mstar_id, date, composition_state, holdings_state,
        pct_holdings_stage_2, pct_holdings_stage_3, pct_holdings_stage_4,
        mean_within_state_rank, n_holdings
    ) VALUES (
        :mstar_id, :date, :composition_state, :holdings_state,
        :pct_holdings_stage_2, :pct_holdings_stage_3, :pct_holdings_stage_4,
        :mean_within_state_rank, :n_holdings
    )
    ON CONFLICT (mstar_id, date) DO UPDATE SET
        composition_state      = EXCLUDED.composition_state,
        holdings_state         = EXCLUDED.holdings_state,
        pct_holdings_stage_2   = EXCLUDED.pct_holdings_stage_2,
        pct_holdings_stage_3   = EXCLUDED.pct_holdings_stage_3,
        pct_holdings_stage_4   = EXCLUDED.pct_holdings_stage_4,
        mean_within_state_rank = EXCLUDED.mean_within_state_rank,
        n_holdings             = EXCLUDED.n_holdings,
        computed_at            = CURRENT_TIMESTAMP
""")


def persist_fund_state_v2(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a DataFrame of fund aggregate rows. Returns the row count."""
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    with engine.begin() as c:
        c.execute(_FUND_UPSERT_SQL, records)
    return len(records)


_ETF_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_etf_state_v2 (
        etf_ticker, date, dominant_state, dominant_share,
        n_holdings, mean_rs_rank_12m,
        pct_stage_2, pct_stage_3, pct_stage_4
    ) VALUES (
        :etf_ticker, :date, :dominant_state, :dominant_share,
        :n_holdings, :mean_rs_rank_12m,
        :pct_stage_2, :pct_stage_3, :pct_stage_4
    )
    ON CONFLICT (etf_ticker, date) DO UPDATE SET
        dominant_state    = EXCLUDED.dominant_state,
        dominant_share    = EXCLUDED.dominant_share,
        n_holdings        = EXCLUDED.n_holdings,
        mean_rs_rank_12m  = EXCLUDED.mean_rs_rank_12m,
        pct_stage_2       = EXCLUDED.pct_stage_2,
        pct_stage_3       = EXCLUDED.pct_stage_3,
        pct_stage_4       = EXCLUDED.pct_stage_4,
        computed_at       = CURRENT_TIMESTAMP
""")


def persist_etf_state_v2(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a DataFrame of ETF aggregate rows. Returns the row count."""
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    with engine.begin() as c:
        c.execute(_ETF_UPSERT_SQL, records)
    return len(records)
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/intelligence/aggregations/test_persistence.py -v
```

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/aggregations/persistence.py tests/intelligence/aggregations/test_persistence.py
git commit -m "feat(aggregations): UPSERT writers for atlas_*_state_v2 tables"
```

---

## Phase 4 — IC harness for legacy signals (1 day CC)

Goal: a single command runs the IC engine against the legacy signals we conditionally kept (CTS PPC/NPC/Contraction continuous values, nav_state, transition/breakout triggers). Results land in `atlas_component_validation` with `component_kind='legacy_candidate'` so later phases know which to keep.

### Task 4.1: Migration 087 — extend `atlas_component_validation` with `component_kind`

- [ ] **Step 1: Write failing test**

Append to `tests/migrations/test_signal_unified_views.py`:

```python
def test_atlas_component_validation_has_component_kind(engine: Engine) -> None:
    with engine.connect() as c:
        cols = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='atlas' AND table_name='atlas_component_validation'
        """)).fetchall()
    names = {r.column_name for r in cols}
    assert "component_kind" in names
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Write migration 087**

Create `migrations/versions/087_legacy_signal_validation_kind.py`:

```python
"""Add component_kind to atlas_component_validation.

Revision ID: 087_legacy_validation_kind
Revises: 086_atlas_etf_state_v2_table
Create Date: 2026-05-18
"""
import sqlalchemy as sa
from alembic import op


revision = "087_legacy_validation_kind"
down_revision = "086_atlas_etf_state_v2_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "atlas_component_validation",
        sa.Column(
            "component_kind",
            sa.String(32),
            nullable=False,
            server_default="state_engine_tier",
        ),
        schema="atlas",
    )
    op.create_check_constraint(
        "ck_component_kind",
        "atlas_component_validation",
        "component_kind IN ('state_engine_tier','legacy_candidate')",
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_constraint("ck_component_kind", "atlas_component_validation",
                       type_="check", schema="atlas")
    op.drop_column("atlas_component_validation", "component_kind", schema="atlas")
```

- [ ] **Step 4: Apply locally + EC2**

- [ ] **Step 5: Run test — expect pass**

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/087_legacy_signal_validation_kind.py tests/migrations/test_signal_unified_views.py
git commit -m "feat(signal-consolidation): component_kind on atlas_component_validation"
```

### Task 4.2: IC harness module

**Files:**
- Create: `atlas/intelligence/states/ic_harness.py`
- Test: `tests/intelligence/states/test_ic_harness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/intelligence/states/test_ic_harness.py`:

```python
"""Tests for atlas/intelligence/states/ic_harness.py."""
import pandas as pd
import pytest

from atlas.intelligence.states.ic_harness import (
    LegacySignal,
    LEGACY_SIGNAL_CATALOG,
    classify_ic_status,
)


def test_classify_ic_status_validated_when_ir_gt_pt4_and_spread_gt_pt005() -> None:
    assert classify_ic_status(ic_ir=0.55, q5_q1_spread=0.04) == "validated"


def test_classify_ic_status_validated_inverse_when_negative_ir_gt_pt4() -> None:
    assert classify_ic_status(ic_ir=-0.48, q5_q1_spread=-0.03) == "validated_inverse"


def test_classify_ic_status_weak_when_ir_pt2_to_pt4() -> None:
    assert classify_ic_status(ic_ir=0.25, q5_q1_spread=0.01) == "weak"


def test_classify_ic_status_decorative_when_ir_lt_pt2() -> None:
    assert classify_ic_status(ic_ir=0.10, q5_q1_spread=0.001) == "decorative"


def test_legacy_signal_catalog_includes_cts_and_nav_state() -> None:
    names = {sig.name for sig in LEGACY_SIGNAL_CATALOG}
    assert "cts_ppc_continuous" in names
    assert "cts_npc_continuous" in names
    assert "cts_contraction_continuous" in names
    assert "nav_state" in names
    assert "transition_trigger" in names
    assert "breakout_trigger" in names


def test_legacy_signal_dataclass_has_loader_and_horizon() -> None:
    sig = LEGACY_SIGNAL_CATALOG[0]
    assert isinstance(sig, LegacySignal)
    assert sig.horizon_days in (21, 63)
    assert callable(sig.loader)
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/intelligence/states/test_ic_harness.py -v
```

- [ ] **Step 3: Implement ic_harness.py**

Create `atlas/intelligence/states/ic_harness.py`:

```python
"""One-shot IC validation for legacy candidate signals.

Each entry in LEGACY_SIGNAL_CATALOG names a legacy signal we want to either
fold into the state engine (as Tier 1 / Tier 2 / Tier 3 input) or cut.
The harness runs the standard IC engine against forward returns, computes
status per the 4-class rule, and persists results to atlas_component_validation
with component_kind='legacy_candidate'.

Status rules (consistent with state_validator.py):
  IR  > 0.4 AND |spread| > 0.005 → validated
  IR < -0.4 AND |spread| > 0.005 → validated_inverse
  0.2 ≤ |IR| ≤ 0.4               → weak
  |IR| < 0.2                     → decorative
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import compute_ic_over_window


# --------------------------------------------------------------------------- #
# Status classification                                                       #
# --------------------------------------------------------------------------- #

def classify_ic_status(ic_ir: float, q5_q1_spread: float) -> str:
    """Map (IR, spread) → 4-class status."""
    if abs(q5_q1_spread) < 0.005:
        return "decorative"
    if ic_ir > 0.4:
        return "validated"
    if ic_ir < -0.4:
        return "validated_inverse"
    if abs(ic_ir) >= 0.2:
        return "weak"
    return "decorative"


# --------------------------------------------------------------------------- #
# Legacy signal catalog                                                       #
# --------------------------------------------------------------------------- #

def _load_cts_continuous(engine: Engine, start: dt.date, end: dt.date, col: str) -> pd.DataFrame:
    """Load a CTS continuous panel from atlas_cts_stock_signals."""
    sql = text(f"""
        SELECT instrument_id::text AS instrument_id, signal_date AS date,
               {col}::float8 AS factor
        FROM atlas.atlas_cts_stock_signals
        WHERE signal_date BETWEEN :s AND :e AND {col} IS NOT NULL
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"s": start, "e": end})
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index(["date", "instrument_id"])[["factor"]]


def _load_legacy_state_panel(engine: Engine, start: dt.date, end: dt.date, col: str) -> pd.DataFrame:
    """Load a legacy boolean state column as 0/1 factor."""
    sql = text(f"""
        SELECT instrument_id::text AS instrument_id, date,
               CASE WHEN {col} THEN 1.0 ELSE 0.0 END AS factor
        FROM atlas.atlas_stock_states_daily
        WHERE date BETWEEN :s AND :e AND {col} IS NOT NULL
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"s": start, "e": end})
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index(["date", "instrument_id"])[["factor"]]


@dataclass(frozen=True)
class LegacySignal:
    name: str
    horizon_days: int
    loader: Callable[[Engine, dt.date, dt.date], pd.DataFrame]
    description: str


LEGACY_SIGNAL_CATALOG: list[LegacySignal] = [
    LegacySignal(
        "cts_ppc_continuous", 21,
        lambda e, s, end: _load_cts_continuous(e, s, end, "ppc_score"),
        "CTS PPC continuous score; tier collapse decorative.",
    ),
    LegacySignal(
        "cts_npc_continuous", 21,
        lambda e, s, end: _load_cts_continuous(e, s, end, "npc_score"),
        "CTS NPC continuous score; tier collapse decorative.",
    ),
    LegacySignal(
        "cts_contraction_continuous", 21,
        lambda e, s, end: _load_cts_continuous(e, s, end, "contraction_score"),
        "CTS contraction continuous score; tier collapse decorative.",
    ),
    LegacySignal(
        "transition_trigger", 21,
        lambda e, s, end: _load_legacy_state_panel(e, s, end, "transition_trigger"),
        "Legacy transition trigger boolean (stage_1 → stage_2 setup).",
    ),
    LegacySignal(
        "breakout_trigger", 21,
        lambda e, s, end: _load_legacy_state_panel(e, s, end, "breakout_trigger"),
        "Legacy breakout trigger boolean.",
    ),
    LegacySignal(
        "nav_state", 63,
        lambda e, s, end: pd.DataFrame(),  # nav_state validation is fund-level; placeholder for fund harness
        "Fund-internal NAV vs category state; needs fund-level forward returns.",
    ),
]


# --------------------------------------------------------------------------- #
# Run + persist                                                               #
# --------------------------------------------------------------------------- #

def run_legacy_ic_harness(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    signals: list[LegacySignal] | None = None,
) -> pd.DataFrame:
    """Run the IC engine against each legacy candidate and return results."""
    if signals is None:
        signals = LEGACY_SIGNAL_CATALOG
    prices = load_price_matrix(engine, start_date=start, end_date=end)
    fwd = compute_forward_returns(prices, periods=[21, 63])
    out_rows: list[dict[str, object]] = []
    for sig in signals:
        factor = sig.loader(engine, start, end)
        if factor.empty:
            out_rows.append({
                "name": sig.name, "horizon_days": sig.horizon_days,
                "mean_ic": None, "ic_ir": None, "q5_q1_spread": None,
                "n_observations": 0, "status": "decorative",
            })
            continue
        ret_wide = fwd[f"return_{sig.horizon_days}d"]
        ic = compute_ic_over_window(factor, ret_wide)
        ir = ic.mean_ic / ic.ic_std if ic.ic_std and ic.ic_std > 0 else 0.0
        spread = ic.q5_q1_spread if hasattr(ic, "q5_q1_spread") else 0.0
        out_rows.append({
            "name": sig.name, "horizon_days": sig.horizon_days,
            "mean_ic": float(ic.mean_ic), "ic_ir": float(ir),
            "q5_q1_spread": float(spread),
            "n_observations": int(ic.n_observations),
            "status": classify_ic_status(ir, spread),
        })
    return pd.DataFrame(out_rows)


_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_component_validation (
        as_of_date, component_name, badge, threshold_range, implied_action,
        horizon_days, mean_ic, ic_ir, q5_q1_spread, status, component_kind
    ) VALUES (
        :as_of_date, :name, 'Continuous', 'continuous', 'investigate',
        :horizon_days, :mean_ic, :ic_ir, :q5_q1_spread, :status, 'legacy_candidate'
    )
    ON CONFLICT (as_of_date, component_name, badge) DO UPDATE SET
        mean_ic        = EXCLUDED.mean_ic,
        ic_ir          = EXCLUDED.ic_ir,
        q5_q1_spread   = EXCLUDED.q5_q1_spread,
        status         = EXCLUDED.status,
        component_kind = EXCLUDED.component_kind
""")


def persist_legacy_ic_results(engine: Engine, df: pd.DataFrame, as_of_date: dt.date) -> int:
    """Persist results to atlas_component_validation with component_kind='legacy_candidate'."""
    if df.empty:
        return 0
    records = [{"as_of_date": as_of_date, **row} for row in df.to_dict(orient="records")]
    with engine.begin() as c:
        c.execute(_UPSERT_SQL, records)
    return len(records)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/intelligence/states/test_ic_harness.py -v
```

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/states/ic_harness.py tests/intelligence/states/test_ic_harness.py
git commit -m "feat(states): ic_harness — validate legacy candidate signals"
```

### Task 4.3: CLI wiring + run

**Files:**
- Modify: `atlas/trading/cli_states.py` (add `validate-legacy` subcommand)

- [ ] **Step 1: Append the new subcommand**

Edit `atlas/trading/cli_states.py` to register `validate-legacy`:

```python
@states_group.command("validate-legacy")
@click.option("--start", type=str, default="2023-01-01",
              help="ISO start date of IC window.")
@click.option("--end", type=str, default="2024-12-31",
              help="ISO end date of IC window.")
@click.option("--persist/--no-persist", default=True,
              help="Persist results to atlas_component_validation.")
def cmd_validate_legacy(start: str, end: str, persist: bool) -> None:
    """Validate legacy candidate signals (CTS, triggers) via IC engine."""
    from datetime import date, datetime
    from atlas.db import get_engine
    from atlas.intelligence.states.ic_harness import (
        run_legacy_ic_harness, persist_legacy_ic_results,
    )

    eng = get_engine()
    start_d = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date()
    df = run_legacy_ic_harness(eng, start_d, end_d)
    click.echo(df.to_string(index=False))
    if persist:
        n = persist_legacy_ic_results(eng, df, as_of_date=date.today())
        click.echo(f"\nPersisted {n} rows to atlas_component_validation.")
```

- [ ] **Step 2: Run locally**

```bash
atlas-lab states validate-legacy --start 2023-01-01 --end 2024-12-31
```
Expected: a 5-row table with name, horizon_days, ic_ir, status. nav_state row has `n_observations=0` (placeholder, fund-level harness deferred).

- [ ] **Step 3: Run on EC2 (canonical data)**

```bash
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/python -m atlas.trading.cli states validate-legacy --start 2023-01-01 --end 2024-12-31 2>&1 | tee /tmp/legacy-ic.txt"
scp atlas:/tmp/legacy-ic.txt docs/audits/legacy-signal-ic-2026-05.txt
```

- [ ] **Step 4: Capture findings in the audit doc**

Append a section to `docs/audits/state-engine-phase2-ic-2026-05.md`:

```markdown
## Phase 4 — Legacy candidate IC (2026-05-XX)

Run via `atlas-lab states validate-legacy --start 2023-01-01 --end 2024-12-31`.

| Signal | Horizon | IR | Status |
|---|---|---|---|
| (from /tmp/legacy-ic.txt, paste rows) |

### Verdicts
- `cts_ppc_continuous` — [keep/cut] — [reason]
- `cts_npc_continuous` — [keep/cut]
- `cts_contraction_continuous` — [keep/cut]
- `transition_trigger` — [keep/cut]
- `breakout_trigger` — [keep/cut]
- `nav_state` — defer (fund-level harness)
```

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/cli_states.py docs/audits/state-engine-phase2-ic-2026-05.md docs/audits/legacy-signal-ic-2026-05.txt
git commit -m "feat(states): atlas-lab states validate-legacy + IC verdicts"
```

---

## Phase 5 — Cut dead frontend chips (1 day CC)

Goal: delete legacy chip files and their references. No DB changes. The state engine is the only signal source; legacy chips no longer have a place.

### Task 5.1: Delete StateTuple4 and references

**Files:**
- Modify: `frontend/src/lib/stock-formatters.tsx` (remove `StateTuple4` export)
- Modify: `frontend/src/components/stocks/StockDeepDiveHeader.tsx` (remove import + usage)

- [ ] **Step 1: Find every reference**

```bash
grep -rln "StateTuple4" frontend/src/
```
Expected: 2 files — `lib/stock-formatters.tsx` (declares), `components/stocks/StockDeepDiveHeader.tsx` (uses).

- [ ] **Step 2: Remove from StockDeepDiveHeader.tsx**

Edit `frontend/src/components/stocks/StockDeepDiveHeader.tsx`:

Remove the `StateTuple4` import on line 4 (already updated in prior commits — header has the import to keep the spec aligned). Remove the `<StateTuple4 ... />` JSX block on lines 34-38. Replace with nothing (the master state card now lives elsewhere).

- [ ] **Step 3: Remove from lib/stock-formatters.tsx**

Edit `frontend/src/lib/stock-formatters.tsx`. Locate the `StateTuple4` function (around line 163) and delete the function body plus its exports.

- [ ] **Step 4: Build to verify nothing else imports it**

```bash
cd frontend && npm run build
```
Expected: build passes. If TypeScript errors, grep for remaining imports.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/stock-formatters.tsx frontend/src/components/stocks/StockDeepDiveHeader.tsx
git commit -m "chore(frontend): drop StateTuple4 — subsumed by MasterStateCard"
```

### Task 5.2: Delete StateJourneyCompact + FundStateJourneyCompact + states-compact API + fund-states-compact API

**Files:**
- Delete: `frontend/src/components/ui/StateJourneyCompact.tsx`
- Delete: `frontend/src/components/funds/FundStateJourneyCompact.tsx`
- Delete: `frontend/src/app/api/states-compact/route.ts`
- Delete: `frontend/src/app/api/fund-states-compact/route.ts`
- Delete corresponding `__tests__/` files

- [ ] **Step 1: Find every reference to StateJourneyCompact**

```bash
grep -rln "StateJourneyCompact\|FundStateJourneyCompact\|states-compact\|fund-states-compact" frontend/src/
```

- [ ] **Step 2: Delete the components and routes**

```bash
git rm frontend/src/components/ui/StateJourneyCompact.tsx \
       frontend/src/components/funds/FundStateJourneyCompact.tsx \
       frontend/src/app/api/states-compact/route.ts \
       frontend/src/app/api/fund-states-compact/route.ts
git rm -r frontend/src/components/ui/__tests__/StateJourneyCompact.test.tsx 2>/dev/null || true
```

- [ ] **Step 3: Remove imports from every consumer**

For each file from Step 1 (excluding the deleted files), open it and remove the `StateJourneyCompact` / `FundStateJourneyCompact` imports and the JSX that used them. Replace with the `DwellTimeline` component for stock pages (already shipping) or simply remove on sector / fund pages until those pages are properly rewired in Phase 8.

- [ ] **Step 4: Build to verify**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/
git commit -m "chore(frontend): drop StateJourneyCompact + compact-state APIs"
```

### Task 5.3: Delete SignalCell + all CTS components + StockHistoryTab

**Files:**
- Delete: `frontend/src/components/stocks/SignalCell.tsx`
- Delete: `frontend/src/components/stocks/CTS*.tsx` (6 files)
- Delete: `frontend/src/components/stocks/StockHistoryTab.tsx`
- Delete: `frontend/src/app/api/cts/index-timing/route.ts`
- Delete: `frontend/src/app/api/cts/sectors/route.ts`
- Delete: `frontend/src/app/api/stocks/[symbol]/cts-brief/route.ts`
- Delete corresponding `__tests__/` files

- [ ] **Step 1: Find every reference**

```bash
grep -rln "SignalCell\|CTSDeepDiveCard\|CTSGradeSummaryCards\|CTSIndexTimingPanel\|CTSSectorPanel\|CTSSignalBadge\|CTSTimingCell\|StockHistoryTab\|/api/cts/" frontend/src/
```

- [ ] **Step 2: Delete files**

```bash
git rm frontend/src/components/stocks/SignalCell.tsx \
       frontend/src/components/stocks/CTS*.tsx \
       frontend/src/components/stocks/StockHistoryTab.tsx
git rm -r frontend/src/app/api/cts/ 2>/dev/null || true
git rm -r frontend/src/app/api/stocks/[symbol]/cts-brief 2>/dev/null || true
git rm frontend/src/components/stocks/__tests__/CTS*.test.tsx 2>/dev/null || true
```

- [ ] **Step 3: Remove imports + JSX from consumers**

For each consumer file from Step 1: remove the imports and JSX. For `StockOverviewTab.tsx`, the CTS Timing Setup card goes away entirely. For `StockScreener.tsx`, the CTS columns go away.

- [ ] **Step 4: Build to verify**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/
git commit -m "chore(frontend): drop SignalCell + CTS components + StockHistoryTab — subsumed by state engine"
```

---

## Phase 6 — Replace chips with ValidatedBadge + WithinStateRankCell (1 day CC)

Goal: every remaining chip that displays a state-derived value reads through `atlas_stock_signal_unified` and renders via `ValidatedBadge` per `atlas_component_validation`.

### Task 6.1: Replace ConvictionCell with WithinStateRankCell

**Files:**
- Rename: `frontend/src/components/stocks/ConvictionCell.tsx` → `WithinStateRankCell.tsx`
- Modify: every consumer

- [ ] **Step 1: Find consumers**

```bash
grep -rln "ConvictionCell" frontend/src/
```

- [ ] **Step 2: Write failing test**

Create `frontend/src/components/stocks/__tests__/WithinStateRankCell.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WithinStateRankCell } from '../WithinStateRankCell'

describe('WithinStateRankCell', () => {
  it('renders the within-state rank value to 2 decimals', () => {
    render(<WithinStateRankCell value={0.7234} />)
    expect(screen.getByText('0.72')).toBeInTheDocument()
  })

  it('renders em-dash for null', () => {
    render(<WithinStateRankCell value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run — expect fail**

```bash
cd frontend && npx vitest run src/components/stocks/__tests__/WithinStateRankCell.test.tsx
```

- [ ] **Step 4: Rename and implement**

```bash
git mv frontend/src/components/stocks/ConvictionCell.tsx frontend/src/components/stocks/WithinStateRankCell.tsx
```

Edit the renamed file to expose `WithinStateRankCell`:

```typescript
// frontend/src/components/stocks/WithinStateRankCell.tsx
// Renders within_state_rank (0..1) as a 2-decimal number with a tiny
// progress bar. Replaces ConvictionCell — same visual real-estate, but
// the value now comes from the IC-validated state engine.

interface Props {
  value: number | null
}

export function WithinStateRankCell({ value }: Props) {
  if (value === null || value === undefined) {
    return <span className="font-mono text-xs text-ink-tertiary">—</span>
  }
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div
        className="h-1.5 flex-1 bg-paper-rule rounded-sm overflow-hidden"
        data-testid="wsr-track"
      >
        <div
          className="h-full bg-signal-pos"
          style={{ width: `${pct}%` }}
          data-testid="wsr-fill"
        />
      </div>
      <span className="font-mono text-xs text-ink-primary tabular-nums">
        {value.toFixed(2)}
      </span>
    </div>
  )
}
```

- [ ] **Step 5: Update every consumer**

For each consumer file from Step 1: change the import path and the JSX. Where the consumer fetched `conviction_score, tier` from `atlas_stock_conviction_daily`, switch the query to read `within_state_rank` from `atlas_stock_signal_unified`. Where a `tier` label was rendered separately, drop it.

- [ ] **Step 6: Run tests + build**

```bash
cd frontend && npx vitest run src/components/stocks && npm run build
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/
git commit -m "feat(frontend): WithinStateRankCell replaces ConvictionCell — IC-derived signal"
```

### Task 6.2: Add `ValidatedBadge`-based RS state chip

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx` (replace inline RS-state span with `ValidatedBadge`)

Note: the dedicated `RSStateChip.tsx` file the spec mentions does not exist as a separate file in the repo — RS-state rendering is inline in screener cells via `rs_state` column. We swap inline.

- [ ] **Step 1: Find inline rs_state renderers**

```bash
grep -n "rs_state" frontend/src/components/stocks/StockScreener.tsx frontend/src/components/etfs/ETFScreener.tsx
```

- [ ] **Step 2: Replace each with `ValidatedBadge`**

For each location, the cell becomes:

```tsx
<ValidatedBadge
  label={row.rs_state ?? '—'}
  validation={validations.find(v => v.component_name === 'rs' && v.badge === row.rs_state) ?? undefined}
/>
```

`validations` is the result of `getComponentValidations()` fetched at the page shell level and passed into the screener as a prop.

- [ ] **Step 3: Plumb `validations` from page shell**

In `frontend/src/app/stocks/page.tsx` and `frontend/src/app/etfs/page.tsx`, fetch validations in parallel with the existing data and pass to the screener:

```tsx
const [data, validations] = await Promise.all([
  getStocksList(),
  getComponentValidations(),
])
return <StockScreener data={data} validations={validations} />
```

- [ ] **Step 4: Build + smoke test**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/
git commit -m "feat(frontend): RS state cells route through ValidatedBadge per-tier IC"
```

### Task 6.3: Same treatment for Risk

- [ ] **Step 1: Find inline risk_state renderers**

```bash
grep -n "risk_state" frontend/src/components/stocks/StockScreener.tsx
```

- [ ] **Step 2: Replace inline span with `ValidatedBadge` keyed on `realized_vol_63` tier**

The screener doesn't yet have `realized_vol_63_tier` from the new engine. Two options: (a) keep `risk_state` rendered via legacy column from the bridge view (it derives from realized_vol_63 once Phase 8 wires the new compute), or (b) drop the column for now and re-add in Phase 8. Choose (a) — the bridge view already maps; the badge just reads `validations[component_name='risk', badge=row.risk_state]`.

- [ ] **Step 3: Build + commit**

```bash
cd frontend && npm run build
git add -A
git commit -m "feat(frontend): risk state cells route through ValidatedBadge"
```

---

## Phase 7 — Query rewire to unified views (2 days CC)

Goal: every `frontend/src/lib/queries/*.ts` file that previously read from `atlas_stock_states_daily` (or `atlas_sector_states_daily`, etc.) now reads from `atlas_stock_signal_unified` (or the analogous sector/fund/ETF view). Columns names stay the same; the view re-derives them.

### Task 7.1: Rewire stocks.ts

**Files:**
- Modify: `frontend/src/lib/queries/stocks.ts`

- [ ] **Step 1: Find every `atlas_stock_states_daily` reference in the file**

```bash
grep -n "atlas_stock_states_daily" frontend/src/lib/queries/stocks.ts
```

- [ ] **Step 2: Replace each with `atlas_stock_signal_unified`**

For each SQL string in the file, swap `atlas.atlas_stock_states_daily` → `atlas.atlas_stock_signal_unified`. The view exposes the same legacy column names (`rs_state`, `momentum_state`, `is_investable`, `weinstein_gate_pass`) so the calling code doesn't change.

Special case: `history_gate_pass`, `liquidity_gate_pass` — these are not in the bridge view. Replace them in SELECT clauses with literal `TRUE AS history_gate_pass, TRUE AS liquidity_gate_pass` until Phase 8 cuts the columns from the rendered output entirely.

- [ ] **Step 3: Replace `atlas_stock_decisions_daily` similarly**

The decisions table contains `is_investable`, `strength_gate`, `direction_gate`, etc. The bridge view derives `is_investable`; the other gates we're cutting. Replace each SELECT of these columns with literal `TRUE AS strength_gate, TRUE AS direction_gate, TRUE AS risk_gate, TRUE AS volume_gate` in the queries until Phase 8 strips the gate row from the screener.

- [ ] **Step 4: Vitest sanity**

```bash
cd frontend && npx vitest run src/lib/queries
```
Expected: existing tests pass (queries return the same shape).

- [ ] **Step 5: Build**

```bash
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/queries/stocks.ts
git commit -m "feat(frontend): stocks queries route through atlas_stock_signal_unified"
```

### Task 7.2: Rewire sectors.ts

**Files:** `frontend/src/lib/queries/sectors.ts`, `frontend/src/lib/queries/sector-deep-dive.ts`, `frontend/src/lib/queries/sector-funds.ts`

- [ ] **Step 1:** Grep `grep -n "atlas_stock_states_daily\|atlas_sector_states_daily\|atlas_cts_" frontend/src/lib/queries/sectors.ts frontend/src/lib/queries/sector-deep-dive.ts frontend/src/lib/queries/sector-funds.ts`
- [ ] **Step 2:** Replace each `FROM atlas.atlas_stock_states_daily` → `FROM atlas.atlas_stock_signal_unified`, each `FROM atlas.atlas_sector_states_daily` → `FROM atlas.atlas_sector_signal_unified`, each `FROM atlas.atlas_cts_sector_pivot_daily` → drop the entire query (CTS deprecated; replace JSX consumer with `null` or `n/a` until Phase 8 cleanup)
- [ ] **Step 3:** Build: `cd frontend && npm run build`
- [ ] **Step 4:** Commit: `git add frontend/src/lib/queries/sectors.ts frontend/src/lib/queries/sector-deep-dive.ts frontend/src/lib/queries/sector-funds.ts && git commit -m "feat(frontend): sector queries through unified view"`

### Task 7.3: Rewire funds.ts

**Files:** `frontend/src/lib/queries/funds.ts`

- [ ] **Step 1:** Grep `grep -n "atlas_fund_states_daily\|atlas_stock_states_daily" frontend/src/lib/queries/funds.ts`
- [ ] **Step 2:** Replace `FROM atlas.atlas_fund_states_daily` → `FROM atlas.atlas_fund_signal_unified` for composition/holdings/recommendation queries. For nav_state-specific queries, keep `atlas_fund_states_daily` (nav_state is retained there per the consolidation spec).
- [ ] **Step 3:** Build: `cd frontend && npm run build`
- [ ] **Step 4:** Commit: `git add frontend/src/lib/queries/funds.ts && git commit -m "feat(frontend): fund queries through unified view (nav_state retained)"`

### Task 7.4: Rewire etfs.ts

**Files:** `frontend/src/lib/queries/etfs.ts`

- [ ] **Step 1:** Grep `grep -n "atlas_etf_states_daily\|atlas_stock_states_daily" frontend/src/lib/queries/etfs.ts`
- [ ] **Step 2:** Replace `FROM atlas.atlas_etf_states_daily` → `FROM atlas.atlas_etf_signal_unified` and `FROM atlas.atlas_stock_states_daily` → `FROM atlas.atlas_stock_signal_unified`
- [ ] **Step 3:** Build: `cd frontend && npm run build`
- [ ] **Step 4:** Commit: `git add frontend/src/lib/queries/etfs.ts && git commit -m "feat(frontend): ETF queries through unified view"`

### Task 7.5: Rewire conviction.ts, global.ts, us-*.ts, instruments.ts, health.ts

**Files:** `frontend/src/lib/queries/conviction.ts`, `global.ts`, `us-stocks.ts`, `us-etfs.ts`, `us-sectors.ts`, `instruments.ts`, `health.ts`

- [ ] **Step 1:** Grep all six files in one pass: `grep -n "atlas_stock_states_daily\|atlas_stock_conviction_daily\|atlas_cts_" frontend/src/lib/queries/conviction.ts frontend/src/lib/queries/global.ts frontend/src/lib/queries/us-stocks.ts frontend/src/lib/queries/us-etfs.ts frontend/src/lib/queries/us-sectors.ts frontend/src/lib/queries/instruments.ts frontend/src/lib/queries/health.ts`
- [ ] **Step 2:** For `conviction.ts` specifically: every query reading `atlas_stock_conviction_daily.conviction_score / tier` now reads `atlas_stock_signal_unified.within_state_rank`. Rename returned property from `conviction_score` → `within_state_rank` if the consumer (WithinStateRankCell) reads the new name.
- [ ] **Step 3:** For the remaining files: replace `atlas_stock_states_daily` → `atlas_stock_signal_unified`; `atlas_cts_*` references → drop (return empty array).
- [ ] **Step 4:** Build + run all vitest query tests: `cd frontend && npm run build && npx vitest run src/lib/queries`
- [ ] **Step 5:** Commit: `git add frontend/src/lib/queries/ && git commit -m "feat(frontend): residual queries through unified view; conviction → within_state_rank"`

After all files complete:

- [ ] **Final step: Smoke test on EC2**

```bash
scp frontend/src/lib/queries/*.ts atlas:/home/ubuntu/atlas-frontend/frontend/src/lib/queries/
ssh atlas "cd /home/ubuntu/atlas-frontend && npm run build && pm2 restart atlas-frontend"
```

Visit https://atlas.jslwealth.in/stocks/NESTLEIND — verify NO contradictions (the legacy "Investable" badge is now derived from the same engine that says "STAGE 4 DECLINE").

---

## Phase 8 — Nightly DAG cutover + page cleanup (3 days CC)

Goal: stop writing to legacy tables. Wire the new engine + aggregators into the nightly DAG. Pages drop gate rows and momentum/volume chips. nav_state retained but separately IC-validated.

### Task 8.1: Disable legacy stocks nightly write

**Files:**
- Modify: `atlas/compute/stocks.py`
- Modify: `scripts/m2_daily.py`

- [ ] **Step 1: Add a no-op flag to `atlas/compute/stocks.py`**

Near the top of `atlas/compute/stocks.py`, find the function `run_stock_daily(...)` and add an early return guard:

```python
LEGACY_NIGHTLY_DISABLED = True  # Phase 8 — state engine writes atlas_stock_state_daily; legacy table frozen.

def run_stock_daily(...) -> dict[str, int]:
    if LEGACY_NIGHTLY_DISABLED:
        log.info("legacy_stocks_nightly_disabled", reason="consolidated to state engine")
        return {"rows_written": 0, "skipped": True}
    # ... existing code below
```

- [ ] **Step 2: Wire state engine into `scripts/m2_daily.py`**

Edit `scripts/m2_daily.py` `main()`. Before the existing `run_stock_daily(...)` line, add:

```python
from atlas.trading.cli_states import classify_and_persist  # noqa: E402

# Phase 8 — state engine is now the canonical stock-day writer.
classify_and_persist(
    as_of_date=args.date,
    persist=True,
    classifier_version="v2.0-validated",
)
```

`classify_and_persist` is a thin Python helper that wraps `atlas-lab states classify --persist`. If that helper doesn't exist yet, add it to `atlas/trading/cli_states.py`.

- [ ] **Step 3: Run the new nightly locally on a sample date**

```bash
python scripts/m2_daily.py --date 2024-12-31
```
Expected: log line `legacy_stocks_nightly_disabled`; state engine reclassifies; no errors.

- [ ] **Step 4: Verify state engine row count**

```bash
psql "$ATLAS_DB_URL" -c "
SELECT COUNT(*) FROM atlas.atlas_stock_state_daily
WHERE date = '2024-12-31' AND classifier_version = 'v2.0-validated'
"
```
Expected: thousands of rows.

- [ ] **Step 5: Commit**

```bash
git add atlas/compute/stocks.py scripts/m2_daily.py atlas/trading/cli_states.py
git commit -m "feat(nightly): state engine becomes canonical stocks-daily writer; legacy frozen"
```

### Task 8.2: Wire sector / fund / ETF aggregators into nightly

**Files:**
- Modify: `atlas/compute/sectors.py` (replace state-classification block with aggregator call)
- Modify: `atlas/compute/etfs.py` (same)
- Modify: `atlas/compute/funds.py` (composition + holdings only; nav_state kept)
- Modify: `scripts/m2_daily.py` / `scripts/m3_daily.py` (add aggregator invocations)

For each compute module:

- [ ] **Step 1: Identify the legacy state-write block**
- [ ] **Step 2: Replace with aggregator + persistence call**

For sectors, after the existing metrics compute, replace the legacy state-classification block with:

```python
from atlas.intelligence.aggregations.sector import (
    aggregate_sector_states, load_stock_panel,
)
from atlas.intelligence.aggregations.persistence import persist_sector_state_v2

panel = load_stock_panel(engine, as_of_date=as_of_date.isoformat())
agg = aggregate_sector_states(panel)
n = persist_sector_state_v2(engine, agg)
log.info("sector_state_v2_persisted", rows=n)
```

For funds (preserving nav_state):

```python
from atlas.intelligence.aggregations.fund import (
    aggregate_fund_composition, load_fund_holdings_panel,
)
from atlas.intelligence.aggregations.persistence import persist_fund_state_v2

holdings_panel = load_fund_holdings_panel(engine, as_of_date=as_of_date.isoformat())
agg = aggregate_fund_composition(holdings_panel)
n = persist_fund_state_v2(engine, agg)
log.info("fund_state_v2_persisted", rows=n)

# Keep the existing nav_state write path — it's a fund-internal NAV computation
# that the bridge view consumes via LEFT JOIN.
```

For ETFs, mirror the sector pattern using `atlas/intelligence/aggregations/etf.py`.

- [ ] **Step 3: Run nightly locally for sample date**

```bash
python scripts/m2_daily.py --date 2024-12-31
python scripts/m3_daily.py --date 2024-12-31  # if separate
```

- [ ] **Step 4: Verify aggregate rows persisted**

```bash
psql "$ATLAS_DB_URL" -c "
SELECT 'sector_v2' AS t, COUNT(*) FROM atlas.atlas_sector_state_v2 WHERE date='2024-12-31'
UNION ALL
SELECT 'fund_v2',    COUNT(*) FROM atlas.atlas_fund_state_v2   WHERE date='2024-12-31'
UNION ALL
SELECT 'etf_v2',     COUNT(*) FROM atlas.atlas_etf_state_v2    WHERE date='2024-12-31'
"
```

- [ ] **Step 5: Commit**

```bash
git add atlas/compute/sectors.py atlas/compute/etfs.py atlas/compute/funds.py scripts/m2_daily.py scripts/m3_daily.py
git commit -m "feat(nightly): bottom-up sector/fund/etf aggregators replace legacy state-classification"
```

### Task 8.3: Strip gate row + momentum/volume chips from StockScreener

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx`

- [ ] **Step 1: Open the file. Find the 7-gate row rendering (rendered as 6-7 colored dots beside each row).**

- [ ] **Step 2: Delete the entire JSX block** that renders the gate dots. Delete any column header for "Gates" / "H L W S D Ri V". Delete the filter checkboxes for those gates from `ScreenerFilterPanel.tsx`.

- [ ] **Step 3: Delete the momentum_state and volume_state cell renderers.** Each cell that referenced these legacy state columns is now empty. Either drop the column entirely or replace with a `ValidatedBadge` for `risk_state` (Phase 2.5 IC-validated tiers).

- [ ] **Step 4: Build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Vitest**

```bash
npx vitest run src/components/stocks
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/stocks/StockScreener.tsx frontend/src/components/stocks/ScreenerFilterPanel.tsx
git commit -m "feat(frontend): drop gate row + momentum/volume chips from StockScreener"
```

### Task 8.4: Strip exit-flag panel from StockDeepDiveBody

**Files:**
- Modify: `frontend/src/components/stocks/StockDeepDiveBody.tsx`

- [ ] **Step 1: Open the file. Find the "Exit Risk Flags" rendering block.**

- [ ] **Step 2: Delete the entire block.** State transitions detected by the engine are the exit signal.

- [ ] **Step 3: Find the Weinstein Stage interpretation panel and Momentum interpretation panel. Delete both** — MasterStateCard covers this on the new layout.

- [ ] **Step 4: Build + vitest**

```bash
cd frontend && npm run build && npx vitest run src/components/stocks
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stocks/StockDeepDiveBody.tsx
git commit -m "feat(frontend): drop exit-flag + Weinstein + Momentum legacy panels"
```

### Task 8.5: Rewire sector pages

**Files:**
- Modify: `frontend/src/components/sectors/SectorOverviewTab.tsx`
- Modify: `frontend/src/components/sectors/SectorStocksTab.tsx`
- Modify: `frontend/src/components/sectors/SectorETFTab.tsx`
- Modify: `frontend/src/components/sectors/SectorDrawerSnapshot.tsx`
- Modify: `frontend/src/lib/queries/sectors.ts`

- [ ] **Step 1: Point `sectors.ts` queries at `atlas_sector_signal_unified`** (already done in Phase 7; verify).

- [ ] **Step 2: Update component props** to use `engine_state`, `dominant_share`, `pct_stage_2`, `pct_stage_3`, `pct_stage_4` from the new view.

- [ ] **Step 3: Map `engine_state` to the existing "Overweight / Neutral / Underweight / Avoid" labels** the user is used to seeing. The bridge view does this in the SQL CASE expression; no JS change needed.

- [ ] **Step 4: Build + smoke test**

```bash
cd frontend && npm run build
```

Visit https://atlas.jslwealth.in/sectors — verify counts match the bottom-up aggregation.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sectors/ frontend/src/lib/queries/sectors.ts
git commit -m "feat(frontend): sector pages read from atlas_sector_signal_unified"
```

### Task 8.6: Rewire fund pages

**Files:**
- Modify: `frontend/src/components/funds/FundPageClient.tsx`, `FundScreener.tsx`, `FundHoldingsTab.tsx`, `FundDeepDiveHeader.tsx`
- Modify: `frontend/src/lib/queries/funds.ts` (already done in Phase 7.3; verify view names match here)

- [ ] **Step 1: Find the 4-gate dot row in FundScreener.tsx**

```bash
grep -n "performance_gate\|sectors_gate\|stocks_gate\|market_gate" frontend/src/components/funds/FundScreener.tsx
```

- [ ] **Step 2: Delete the gate dot block** rendering `performance_gate`, `sectors_gate`, `stocks_gate`, `market_gate`. Delete the column header for "Gates" / "P S H M". Remove related filter checkboxes from the fund screener filter panel if present.

- [ ] **Step 3: Update component props** in FundPageClient.tsx, FundScreener.tsx, FundHoldingsTab.tsx, FundDeepDiveHeader.tsx to consume `composition_state`, `holdings_state`, `nav_state`, `recommendation` from the unified view shape. The view exposes the same names so no JSX changes are needed beyond removing the gates.

- [ ] **Step 4: Build + smoke test**

```bash
cd frontend && npm run build
```

Visit https://atlas.jslwealth.in/funds — verify recommendation column populates from the new view.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/funds/
git commit -m "feat(frontend): fund pages drop gate row; read from atlas_fund_signal_unified"
```

### Task 8.7: Rewire ETF pages

**Files:**
- Modify: `frontend/src/components/etfs/ETFScreener.tsx`, `ETFBubbleChart.tsx`, `ETFSnapshotTiles.tsx`
- Modify: `frontend/src/lib/queries/etfs.ts`

For `ETFBubbleChart.tsx` specifically, re-axis:
- X-axis: was `volatility` → now `atr_14_252d_ratio` (from `atlas_stock_signal_unified`, joined at ETF level via holdings)
- Y-axis: was `ret_3m` → now `within_state_rank` (mean across holdings)
- Bubble color: was `rs_state` → now `engine_state`
- Bubble size: keep `rs_pctile_3m` (continuous, IC-validated as Tier 4)

- [ ] **Step 1: Update queries to fetch the new fields**
- [ ] **Step 2: Update chart axis definitions**
- [ ] **Step 3: Build + visual smoke test**
- [ ] **Step 4: Commit**

### Task 8.8: Global / Portfolios / Strategies / US pages

**Files:**
- Modify: `frontend/src/components/global/GlobalCountryScreener.tsx`, `CountryRankingsTable.tsx`
- Modify: `frontend/src/components/us/USSectorDetailTabs.tsx`
- Modify: Any portfolio / strategy components that consume legacy state columns

These pages mostly inherit the cleanup automatically because they use shared cells. Audit each and confirm:

- [ ] **Step 1: Run grep**

```bash
grep -rln "rs_state\|momentum_state\|risk_state\|volume_state\|is_investable\|weinstein_gate_pass" frontend/src/components/global/ frontend/src/components/us/ frontend/src/app/portfolios/ frontend/src/app/strategies/
```

- [ ] **Step 2: For each match, verify the query routes through the unified view, not the legacy table.** If still hitting legacy table, swap.

- [ ] **Step 3: Build + smoke test all pages**

```bash
cd frontend && npm run build
```

Browse: /global, /global/country/HDFCBANK, /us, /us/sectors/Banking, /portfolios, /strategies, /strategies/[id]. No contradictions.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/
git commit -m "feat(frontend): residual page references route through unified views"
```

### Task 8.9: Deploy + goal-post check

- [ ] **Step 1: Deploy to EC2**

```bash
tar -czf /tmp/atlas-frontend.tgz frontend/src/
scp /tmp/atlas-frontend.tgz atlas:/tmp/
ssh atlas "cd /home/ubuntu/atlas-frontend && tar -xzf /tmp/atlas-frontend.tgz && npm run build && pm2 restart atlas-frontend"
```

- [ ] **Step 2: Run one full nightly cycle on EC2**

```bash
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/python scripts/m2_daily.py --date $(date -d 'yesterday' +%Y-%m-%d)"
```
Expected: state engine writes, three aggregator tables populated.

- [ ] **Step 3: Goal-post check**

```bash
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/python -m atlas.trading.cli goal-post --rank 1"
```
Expected: `met:true`.

---

## Phase 8.10 — Demo handoff to fund manager (0.5 day CC)

Goal: every page on `http://13.206.34.214:3002/` reads exclusively from the new state engine and bridge views. Existing production at `https://atlas.jslwealth.in/` is untouched. Fund manager evaluates side-by-side.

### Task 8.10.1: Final v2 deploy + visual walkthrough

- [ ] **Step 1: Deploy current branch to v2**

```bash
./scripts/deploy_v2.sh
```
Expected: `HTTP 200` from the demo URL.

- [ ] **Step 2: Smoke test the key pages with curl**

```bash
for path in /stocks /stocks/NESTLEIND /stocks/ANANTRAJ /sectors /sectors/Banking /funds /etfs; do
  printf "%-40s " "$path"
  curl -s -o /dev/null -w 'HTTP %{http_code} | %{size_download}b\n' "http://13.206.34.214:3002$path"
done
```
Expected: all HTTP 200, response sizes comparable to production atlas.jslwealth.in.

- [ ] **Step 3: Side-by-side spot check on NESTLEIND**

```bash
curl -s "http://13.206.34.214:3002/stocks/NESTLEIND" > /tmp/v2-nestle.html
curl -s "https://atlas.jslwealth.in/stocks/NESTLEIND"  > /tmp/v1-nestle.html
# Confirm v2 lacks the legacy gate row + has only one state label.
grep -c "history_gate_pass\|weinstein_gate_pass\|liquidity_gate_pass" /tmp/v2-nestle.html
# Expected: 0 (gates gone)
grep -c "STAGE 4 DECLINE\|Stage 4 Decline" /tmp/v2-nestle.html
# Expected: ≥ 1 (master state present)
```

- [ ] **Step 4: Write demo notes**

Create `docs/audits/v2-demo-handoff-2026-05.md`:

```markdown
# Atlas v2 — fund-manager demo

**URL:** http://13.206.34.214:3002/
**Production:** https://atlas.jslwealth.in/

## What changed
- Single state per instrument across every page (no contradictions)
- Gate rows removed from stock + fund screeners
- ConvictionCell replaced with within-state-rank
- Sector / fund / ETF aggregations are bottom-up from stock states
- nav_state retained for funds (genuinely fund-internal)

## Side-by-side
| Page | v1 (atlas.jslwealth.in) | v2 (13.206.34.214:3002) |
|---|---|---|
| /stocks/NESTLEIND | "Investable" + "Stage 4 Decline" (contradicts) | "Stage 4 Decline" only |
| /stocks (list) | 7-gate dot row + Mom + Vol chips | gates gone; rs_state via ValidatedBadge |
| /funds | 4-gate dot row | gates gone; recommendation derived |
| /sectors | top-down sector_state | bottom-up from stock states |

## Evaluation prompts for the fund manager
1. Is the v2 page faster to interpret?
2. Are there any signals you miss from v1 that v2 cuts?
3. Does the "Recommended / Hold / Avoid" derived from new aggregators match your intuition vs the v1 version?
4. Does within_state_rank replace SP04 conviction acceptably?
```

- [ ] **Step 5: Commit the demo notes**

```bash
git add docs/audits/v2-demo-handoff-2026-05.md
git commit -m "docs(demo): v2 handoff notes for fund-manager evaluation"
```

### Task 8.10.2: Decision gate

After the fund manager evaluates:

- **If approved** → merge `feat/atlas-consolidation` → `main`, retire production atlas-frontend on 3001, point `atlas.jslwealth.in` at port 3002 (or rebuild 3001 from main), then run Phase 9 (drop legacy tables) after 2-week burn-in.
- **If iteration needed** → fund-manager feedback lands as new tasks on `feat/atlas-consolidation`. Re-deploy via `./scripts/deploy_v2.sh`. No production impact.
- **If rejected** → preserve `feat/atlas-consolidation` as a research branch; the bridge views + new aggregator tables stay (non-destructive) and become available for any future cleanup attempt.

---

## Phase 9 — Drop legacy tables (1 day CC, applied after 2-week burn-in)

Goal: legacy state tables drop. The bridge views remain; their source data is gone, so they're effectively read-only on the new aggregate tables.

**Gate:** Phase 9 only runs after 14 days of clean nightly cycles on the new aggregators with no UI regressions reported.

### Task 9.1: Migration 088 — drop conviction + CTS tables

**Files:**
- Create: `migrations/versions/088_drop_legacy_state_tables_phase1.py`

- [ ] **Step 1: Write the migration**

```python
"""Drop conviction + CTS tables (Phase 1 of legacy table drop).

Revision ID: 088_drop_legacy_phase1
Revises: 087_legacy_validation_kind
Create Date: 2026-06-XX

Gate: only run after 2-week burn-in verifies no consumer queries these tables.
"""
import sqlalchemy as sa
from alembic import op


revision = "088_drop_legacy_phase1"
down_revision = "087_legacy_validation_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_stock_conviction_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_stock_signals CASCADE")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_index_timing CASCADE")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_sector_pivot_daily CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "Phase 1 legacy drop is one-way; restore from backup if rollback needed."
    )
```

- [ ] **Step 2: Apply locally + EC2**

```bash
alembic upgrade head
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/alembic upgrade head"
```

- [ ] **Step 3: Verify no consumers**

```bash
grep -rln "atlas_stock_conviction_daily\|atlas_cts_" atlas/ scripts/ frontend/src/
```
Expected: no matches (anything remaining → fix before migrating).

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/088_drop_legacy_state_tables_phase1.py
git commit -m "feat(migrations): drop conviction + CTS tables (Phase 1 legacy burn-in passed)"
```

### Task 9.2: Migration 089 — drop legacy state tables

**Files:**
- Create: `migrations/versions/089_drop_legacy_state_tables_phase2.py`

- [ ] **Step 1: Write migration 089**

```python
"""Drop atlas_*_states_daily legacy tables (Phase 2 of legacy table drop).

Revision ID: 089_drop_legacy_phase2
Revises: 088_drop_legacy_phase1
Create Date: 2026-06-XX

Gate: only run after 2-week burn-in verifies no consumer queries these tables.
atlas_fund_states_daily is retained — nav_state continues to live there as a
genuine fund-internal computation outside the state engine's scope.
"""
from alembic import op


revision = "089_drop_legacy_phase2"
down_revision = "088_drop_legacy_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_stock_states_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_sector_states_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_etf_states_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_stock_decisions_daily CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "Phase 2 legacy drop is one-way; restore from backup if rollback needed."
    )
```

- [ ] **Step 2: Verify no consumers**

```bash
grep -rln "atlas_stock_states_daily\|atlas_sector_states_daily\|atlas_etf_states_daily\|atlas_stock_decisions_daily" atlas/ scripts/ frontend/src/
```
Expected: zero matches. If anything still references these tables, fix before proceeding.

- [ ] **Step 3: Apply locally**

```bash
alembic upgrade head
```

- [ ] **Step 4: Apply on EC2**

```bash
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/alembic upgrade head"
```

- [ ] **Step 5: Final goal-post check**

```bash
ssh atlas "cd /home/ubuntu/atlas-os-sl && /home/ubuntu/.venv/bin/python -m atlas.trading.cli goal-post --rank 1"
```
Expected: `met:true`.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/089_drop_legacy_state_tables_phase2.py
git commit -m "feat(migrations): drop atlas_*_states_daily legacy tables (Phase 2 burn-in passed)"
```

---

## Definition of done (mirrors spec §)

1. Every page on atlas.jslwealth.in displays signals derived from `atlas_stock_state_daily` or its aggregates. NESTLEIND shows one consistent state across the entire page.
2. No frontend query reads from `atlas_stock_states_daily`, `atlas_stock_conviction_daily`, `atlas_cts_*`, `atlas_sector_states_daily`, `atlas_etf_states_daily`. (`atlas_fund_states_daily` retained for nav_state.)
3. `atlas-lab goal-post --rank 1` returns `met:true` at the end of every phase.
4. `atlas-lab states validate-legacy` ran once and persisted verdicts; any signal kept (e.g. validated CTS continuous) is wired into `classifier.py` as a Tier 3 transition trigger.
5. Nightly DAG writes only to: `atlas_stock_state_daily`, `atlas_sector_state_v2`, `atlas_fund_state_v2`, `atlas_etf_state_v2`, `atlas_fund_states_daily` (nav_state only), `atlas_component_validation`.
6. Test coverage: every aggregator has unit tests; every view has smoke tests; every deleted component's tests are removed.
7. Hooks pass cleanly on every commit (400 LOC source / 800 LOC tests / 250 LOC page shells).
8. Two-week burn-in completed before Phase 9 drops legacy tables.
