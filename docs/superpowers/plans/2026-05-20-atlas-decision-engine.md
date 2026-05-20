# Atlas v2 Decision Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn Atlas v2 from a set of dashboards into a connected decision tool — a layered-targets + Policy-rails decision flow where a fund manager moves regime → sector → stock → conviction → portfolio action in one continuous path.

**Architecture:** Three waves. Wave 1 wires the existing pages into a navigable flow (no new data model). Wave 2 adds the per-portfolio Policy that constrains every recommendation. Wave 3 adds the Act loop — policy-sized portfolio changes and deterioration surfacing.

**Tech Stack:** Next.js App Router, Tailwind v4, Recharts, Vitest+RTL (frontend); Python 3.12, SQLAlchemy 2.0, Alembic, Postgres (backend).

**Spec:** [2026-05-20-atlas-decision-engine-design.md](../specs/2026-05-20-atlas-decision-engine-design.md)
**Interactivity checklist:** [2026-05-20-atlas-decision-flow-design.md](../specs/2026-05-20-atlas-decision-flow-design.md) Part 3 (the 64-element map).

---

## Cross-cutting acceptance criteria (EVERY task must satisfy these)

Every task's "done" includes, where the task touches a UI element:
- **C1 — Cross-linked:** every ticker / sector / fund / ETF / country / state-badge the task renders is a link or hover-card. Zero static tokens. Use the shared components from Task 1.1 — never hand-roll.
- **C2 — Consistent:** the same concept renders via the same component everywhere. A state badge is `<StateBadge>`, a sector chip is `<LinkedSector>`, a returns cell is `<ReturnCell>`. No divergent one-offs.
- **C3 — Explained:** every metric / badge / column header / chart added gets a tooltip in the SAME task — what it means + how it is computed. Use `<MetricTooltip>` (Task 1.1).
- **C4 — Dense not overwhelming:** information-rich, clear hierarchy, progressive disclosure for optional depth.
- **C5 — Zero synthetic data:** every rendered value traces to a real computed source. Where real data does not exist, render an explicit `n/a` / "data not available" — never fake, interpolate, or extrapolate. A task that surfaces a value must name its source column.
- **C6 — Formulas tested:** any formula gets a unit test asserting the math against hand-computed expected values.
- **C7 — Logic checks:** consistency assertions (weights sum, mutually-exclusive sets, breach detection) each get a test.

A task is not complete until its slice of C1-C7 is met. Reviewers check this explicitly.

---

## File structure

### Wave 1 — new files
- `frontend/src/components/ui/LinkedToken.tsx` — `LinkedTicker`, `LinkedSector`, `LinkedFund`, `LinkedETF`, `LinkedCountry` — the cross-link primitives (≤200 LOC)
- `frontend/src/components/ui/MetricTooltip.tsx` — already exists; extend with a metric-definition registry
- `frontend/src/components/regime/RegimeVerdict.tsx` — the one-line verdict (≤120 LOC)
- `frontend/src/components/regime/SignalScorecard.tsx` — the bottom-up 4-signal scorecard (≤180 LOC)
- `frontend/src/components/regime/TodayWorklist.tsx` — N sectors / N breakouts / N deteriorating, clickable (≤150 LOC)
- `frontend/src/lib/metric-registry.ts` — every metric's name + definition + formula string, one source of truth for tooltips (≤300 LOC)
- `atlas/intelligence/states/dwell_recompute.py` — continuous dwell recompute (≤200 LOC)

### Wave 1 — modified files
- `frontend/src/app/page.tsx` — merge `/intelligence` worklist + add verdict + scorecard
- `frontend/src/components/regime/*` — Trend/Breadth/Momentum/Participation sections gain tooltips + links
- `frontend/src/components/stocks/StockScreener.tsx`, `StockDeepDiveBody.tsx` — cross-link tokens
- `frontend/src/components/sectors/*`, `funds/*`, `etfs/*` — cross-link tokens
- `frontend/src/lib/queries/stocks.ts` — `getAllStocks` accepts a `sectorFilter` param for the step-2→3 handoff

### Wave 2 — new files
- `migrations/versions/092_atlas_portfolio_policy.py`
- `atlas/intelligence/policy/__init__.py`, `policy.py` — load effective policy, validate (≤300 LOC)
- `atlas/intelligence/policy/targets.py` — sector-target derivation (≤250 LOC)
- `frontend/src/lib/queries/policy.ts` — read effective policy for a portfolio
- `frontend/src/components/portfolio/PolicyPanel.tsx` — the config surface (≤350 LOC)
- `tests/intelligence/policy/test_policy.py`, `test_targets.py`

### Wave 3 — new files
- `migrations/versions/093_portfolio_targets_holdings.py`
- `atlas/intelligence/policy/sizing.py` — position-sizing formula (≤200 LOC)
- `atlas/intelligence/policy/compliance.py` — policy-compliance check (≤250 LOC)
- `frontend/src/components/portfolio/ActButton.tsx`, `CurrentVsTarget.tsx`, `DeteriorationPanel.tsx`
- `tests/intelligence/policy/test_sizing.py`, `test_compliance.py`

---

## WAVE 1 — Wiring (navigable flow, no new data model)

### Task 1.1: Cross-link primitives + metric registry

**Files:**
- Create: `frontend/src/lib/metric-registry.ts`
- Create: `frontend/src/components/ui/LinkedToken.tsx`
- Test: `frontend/src/components/ui/__tests__/LinkedToken.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LinkedTicker, LinkedSector } from '../LinkedToken'

describe('LinkedToken', () => {
  it('LinkedTicker renders an anchor to the stock detail route', () => {
    render(<LinkedTicker symbol="ANANTRAJ" />)
    const a = screen.getByRole('link', { name: /ANANTRAJ/ })
    expect(a).toHaveAttribute('href', '/stocks/ANANTRAJ')
  })
  it('LinkedSector renders an anchor to the sector route', () => {
    render(<LinkedSector sector="Banking" />)
    expect(screen.getByRole('link', { name: /Banking/ })).toHaveAttribute('href', '/sectors/Banking')
  })
  it('LinkedTicker with null symbol renders an em-dash, not a broken link', () => {
    render(<LinkedTicker symbol={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })
})
```

- [ ] **Step 2: Run — expect FAIL** (`npx vitest run src/components/ui/__tests__/LinkedToken.test.tsx`)

- [ ] **Step 3: Implement `metric-registry.ts`**

A single map: metric key → `{ label, definition, formula }`. This is the one source of truth for every tooltip (C3). Seed it with every metric the flow surfaces:

```typescript
// frontend/src/lib/metric-registry.ts
export interface MetricDef { label: string; definition: string; formula: string }

export const METRIC_REGISTRY: Record<string, MetricDef> = {
  engine_state: {
    label: 'Stage',
    definition: 'IC-validated Weinstein stage. Stage 1 base · 2A fresh breakout · 2B confirmed · 2C mature · 3 top · 4 decline · uninvestable.',
    formula: 'classify_state_panel() over close vs SMA-50/150/200, ATR contraction, breakout ratio.',
  },
  within_state_rank: {
    label: 'Within-state rank',
    definition: 'Where this instrument ranks among peers in the same Weinstein state today. 0..1, higher = stronger.',
    formula: '0.4·freshness + 0.3·rs_rank_12m + 0.3·realized_vol_rank (migration 078).',
  },
  rs_state: {
    label: 'RS state',
    definition: 'Relative-strength tier from 12-month RS rank. Leader / Strong / Average / Weak / Laggard.',
    formula: 'rs_rank_12m percentile: ≥0.90 Leader · ≥0.70 Strong · ≥0.30 Average · ≥0.10 Weak · else Laggard.',
  },
  risk_state: {
    label: 'Risk',
    definition: 'Volatility tier from 63-day realized volatility, quartiled across the day cohort.',
    formula: 'NTILE(4) OVER (ORDER BY realized_vol_63): Low / Normal / Elevated / High.',
  },
  // ... one entry per metric the flow renders. The implementing engineer
  // extends this as Tasks 1.3-1.7 surface new metrics — each task that adds
  // a metric adds its registry entry in the same commit (C3).
}

export function metric(key: string): MetricDef | null {
  return METRIC_REGISTRY[key] ?? null
}
```

- [ ] **Step 4: Implement `LinkedToken.tsx`**

```tsx
// frontend/src/components/ui/LinkedToken.tsx
import Link from 'next/link'

function dash() {
  return <span className="font-mono text-xs text-ink-tertiary">—</span>
}

export function LinkedTicker({ symbol, className = '' }: { symbol: string | null; className?: string }) {
  if (!symbol) return dash()
  return (
    <Link href={`/stocks/${encodeURIComponent(symbol)}`}
      className={`text-ink-primary hover:text-teal hover:underline transition-colors ${className}`}>
      {symbol}
    </Link>
  )
}

export function LinkedSector({ sector, className = '' }: { sector: string | null; className?: string }) {
  if (!sector) return dash()
  return (
    <Link href={`/sectors/${encodeURIComponent(sector)}`}
      className={`text-ink-secondary hover:text-teal hover:underline transition-colors ${className}`}>
      {sector}
    </Link>
  )
}

export function LinkedFund({ mstarId, name }: { mstarId: string | null; name: string | null }) {
  if (!mstarId || !name) return dash()
  return (
    <Link href={`/funds/${encodeURIComponent(mstarId)}`}
      className="text-ink-primary hover:text-teal hover:underline transition-colors">
      {name}
    </Link>
  )
}

export function LinkedETF({ ticker }: { ticker: string | null }) {
  if (!ticker) return dash()
  return (
    <Link href={`/etfs/${encodeURIComponent(ticker)}`}
      className="text-ink-primary hover:text-teal hover:underline transition-colors">
      {ticker}
    </Link>
  )
}

export function LinkedCountry({ ticker, name }: { ticker: string | null; name: string | null }) {
  if (!ticker || !name) return dash()
  return (
    <Link href={`/global/country/${encodeURIComponent(ticker)}`}
      className="text-ink-primary hover:text-teal hover:underline transition-colors">
      {name}
    </Link>
  )
}
```

- [ ] **Step 5: Run tests — expect 3 PASS.** Build: `cd frontend && npm run build`.

- [ ] **Step 6: Commit** — `git add frontend/src/lib/metric-registry.ts frontend/src/components/ui/LinkedToken.tsx frontend/src/components/ui/__tests__/LinkedToken.test.tsx && git commit -m "feat(decision-engine): cross-link primitives + metric registry"`

### Task 1.2: dwell_days continuous recompute (degeneracy fix)

**Problem:** the monthly-chunk backfill computed `dwell_days` per-chunk, so it never accumulated across month boundaries — cohort baselines are degenerate (~1 day everywhere). Fix: one continuous pass that walks each instrument's full state history and computes true run-length.

**Files:**
- Create: `atlas/intelligence/states/dwell_recompute.py`
- Test: `tests/intelligence/states/test_dwell_recompute.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
from datetime import date
from atlas.intelligence.states.dwell_recompute import recompute_dwell_days

def test_dwell_accumulates_across_a_continuous_run():
    # Same state 5 consecutive trading days -> dwell 0,1,2,3,4
    panel = pd.DataFrame([
        {"instrument_id": "a", "date": date(2025, 1, d), "state": "stage_1"}
        for d in (2, 3, 6, 7, 8)
    ])
    out = recompute_dwell_days(panel)
    assert out["dwell_days"].tolist() == [0, 1, 2, 3, 4]

def test_dwell_resets_on_state_change():
    panel = pd.DataFrame([
        {"instrument_id": "a", "date": date(2025, 1, 2), "state": "stage_1"},
        {"instrument_id": "a", "date": date(2025, 1, 3), "state": "stage_1"},
        {"instrument_id": "a", "date": date(2025, 1, 6), "state": "stage_2a"},
        {"instrument_id": "a", "date": date(2025, 1, 7), "state": "stage_2a"},
    ])
    out = recompute_dwell_days(panel)
    assert out["dwell_days"].tolist() == [0, 1, 0, 1]
```

- [ ] **Step 2: Run — expect FAIL** (`pytest tests/intelligence/states/test_dwell_recompute.py -v`)

- [ ] **Step 3: Implement `recompute_dwell_days`** — sort by (instrument_id, date), within each instrument detect state-change boundaries, dwell = cumulative count since the last change. Plus a `persist_dwell` that UPDATEs `atlas_stock_state_daily.dwell_days` and `state_since_date` in bulk. Vectorized (no iterrows — `data-engineering.md` rule).

```python
"""Continuous dwell-days recompute. The monthly-chunk backfill computed
dwell per-chunk so it never crossed month boundaries; this walks each
instrument's full history once and writes true run-length."""
from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

def recompute_dwell_days(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.sort_values(["instrument_id", "date"]).reset_index(drop=True)
    # New run starts when instrument changes OR state differs from prior row.
    state_change = (df["state"] != df.groupby("instrument_id")["state"].shift())
    run_id = state_change.groupby(df["instrument_id"]).cumsum()
    df["dwell_days"] = df.groupby(["instrument_id", run_id]).cumcount()
    return df

def recompute_and_persist(engine: Engine, classifier_version: str = "v2.0-validated") -> int:
    with engine.connect() as c:
        panel = pd.read_sql(text("""
            SELECT instrument_id::text AS instrument_id, date, state
            FROM atlas.atlas_stock_state_daily
            WHERE classifier_version = :cv
        """), c, params={"cv": classifier_version})
    if panel.empty:
        return 0
    out = recompute_dwell_days(panel)
    records = out[["instrument_id", "date", "dwell_days"]].to_dict("records")
    with engine.begin() as c:
        c.execute(text("""
            UPDATE atlas.atlas_stock_state_daily
            SET dwell_days = :dwell_days
            WHERE instrument_id = :instrument_id::uuid AND date = :date
              AND classifier_version = :cv
        """), [{**r, "cv": classifier_version} for r in records])
    return len(records)
```

- [ ] **Step 4: Run tests — expect 2 PASS.**

- [ ] **Step 5: Run the recompute against the live DB** — `python -c "from atlas.db import get_engine; from atlas.intelligence.states.dwell_recompute import recompute_and_persist; print(recompute_and_persist(get_engine()))"` then re-run `atlas-lab states baselines-refresh`. Verify `atlas_state_dwell_statistics` now has non-degenerate medians (`SELECT cohort_key, state, median_dwell_days, p95_dwell_days FROM atlas.atlas_state_dwell_statistics` — p95 should vary, not all = 1).

- [ ] **Step 6: Wire into the nightly** — add `recompute_and_persist` after the classify step in `scripts/nightly_v2.sh` so dwell stays correct daily.

- [ ] **Step 7: Commit** — `feat(states): continuous dwell recompute — fixes monthly-chunk degeneracy`

### Task 1.3: Regime page — merge worklist + verdict + bottom-up scorecard

The existing `/` is already the regime classifier page (RegimeHeadline + Trend/Breadth/Momentum/Participation). This task ADDS three blocks at the top and merges the `/intelligence` worklist — nothing existing is removed.

**Files:**
- Create: `frontend/src/components/regime/RegimeVerdict.tsx`, `SignalScorecard.tsx`, `TodayWorklist.tsx`
- Modify: `frontend/src/app/page.tsx`
- Create: `frontend/src/lib/queries/regime-scorecard.ts`
- Test: per component

- [ ] **Step 1: Write failing tests** for the 3 components — `RegimeVerdict` renders a single sentence from `(regime_state, deployment_pct, leading_sectors)`; `SignalScorecard` renders 4 tiles (Trend/Breadth/Momentum/Participation) each with a value + `MetricTooltip`; `TodayWorklist` renders 3 clickable counts (N sectors entered favour → `/sectors`, N breakouts → first breakout's `/stocks/[symbol]`, N deteriorating → `/`-anchored list).

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement the 3 components + the scorecard query.** `regime-scorecard.ts` computes the 4 bottom-up signals (C5 — all from real `atlas_stock_signal_unified`):
  - **Trend** = `% of universe in stage_2a/2b/2c` on the latest date
  - **Breadth** = MA participation (`% above EMA-50` from `atlas_market_regime_daily`)
  - **Momentum** = net Stage-2 inflow over 5 trading days (count entering stage_2 − count leaving)
  - **Participation** = `1 − leadership_concentration` averaged across sectors
  Each value carries its source so the tooltip (C3) can state the formula.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Wire into `page.tsx`** — `RegimeVerdict` + `SignalScorecard` + `TodayWorklist` render ABOVE `RegimeHeadline`. The existing 4 sections stay untouched below. Page shell stays ≤250 LOC — the 3 new blocks are components, page just composes.

- [ ] **Step 6: Build + deploy** (`./scripts/deploy_v2.sh`), screenshot `/`, confirm verdict + scorecard + worklist render above the unchanged classifier sections.

- [ ] **Step 7: Commit** — `feat(regime): verdict + bottom-up 4-signal scorecard + worklist on /`

### Task 1.4: Regime page — cross-link the worklist + rotation + breakouts

- [ ] **Step 1:** failing test — `TodayWorklist` sector counts link to `/sectors`, breakout/leader/deterioration tickers use `<LinkedTicker>`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** replace every static ticker/sector token in `TodayWorklist` and the merged `/intelligence` blocks with `<LinkedTicker>` / `<LinkedSector>`. Regime sub-metrics (VIX, A/D, McClellan) get `<MetricTooltip>` from the registry (C3).
- [ ] **Step 4:** run — PASS. Build.
- [ ] **Step 5:** Commit — `feat(regime): worklist + rotation + breakouts fully cross-linked`

### Task 1.5: Stock detail — cross-link every token

- [ ] **Step 1:** failing test — `StockDeepDiveBody` renders sector as `<LinkedSector>`, "N peers in this state" as a link to `/stocks?state=<state>`, index label linked.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** in `StockDeepDiveBody.tsx` + `StockDeepDiveHeader.tsx`, swap static sector/index/peer tokens for the Task 1.1 primitives; state badge gets a `MetricTooltip` (engine_state registry entry); peers-count anchors to the on-page peers table.
- [ ] **Step 4:** run — PASS. Build.
- [ ] **Step 5:** Commit — `feat(stocks): stock detail tokens cross-linked`

### Task 1.6: Sector + ETF + Fund pages — cross-link tokens

- [ ] **Step 1:** failing tests — sector page stock rows use `<LinkedTicker>`; fund/ETF detail composition+holdings stocks use `<LinkedTicker>`; sector chips everywhere use `<LinkedSector>`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** sweep `frontend/src/components/sectors/*`, `funds/*`, `etfs/*` — every ticker/sector/fund token → Task 1.1 primitive. This is the bulk of the 64-element map (C1). Each column header gets a `MetricTooltip` (C3).
- [ ] **Step 4:** run — PASS. Build.
- [ ] **Step 5:** Commit — `feat(sectors,funds,etfs): cross-link all instrument tokens`

### Task 1.7: Step handoff — /stocks pre-filtered from a sector

**Files:** Modify `frontend/src/lib/queries/stocks.ts` (`getAllStocks` gains optional `sectorFilter`), `frontend/src/app/stocks/page.tsx` (reads `?sector=` searchParam), `frontend/src/components/stocks/StockScreener.tsx` (shows a "filtering: Banking" banner + default sort = within_state_rank desc when a sector filter is active).

- [ ] **Step 1:** failing test — `getAllStocks({ sectorFilter: 'Banking' })` returns only Banking instruments; with no filter returns all.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** add the `WHERE (:sector IS NULL OR u.sector = :sector)` clause; page reads the searchParam; screener shows the active-filter banner + conviction-desc default sort.
- [ ] **Step 4:** run — PASS. Build. Verify: from `/sectors/Banking` a "view Banking stocks" link lands on `/stocks?sector=Banking` pre-filtered.
- [ ] **Step 5:** Commit — `feat(flow): /stocks pre-filtered from sector — step 2→3 handoff`

### Task 1.8: Honest data labelling (C5 enforcement)

The 087 hotfix views fall back fund + ETF `signal_unified` to LEGACY state tables. Per C5, surface this honestly.

- [ ] **Step 1:** failing test — a fund row whose data is legacy-sourced renders a small "legacy" provenance marker; the 17 commodity ETFs render `engine_state` as "n/a — commodity" not a fake stage.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** add a `data_source` field to the fund/ETF row types (`bottom_up` vs `legacy`); render a subtle provenance dot with a tooltip explaining the source; commodity ETFs (no equity holdings) show `n/a — commodity ETF, no equity constituents`. No fabricated states anywhere.
- [ ] **Step 4:** run — PASS. Build.
- [ ] **Step 5:** Commit — `feat(data-integrity): honest provenance labelling — no synthetic states`

---

## WAVE 2 — The Policy

### Task 2.1: Migration 092 — `atlas_portfolio_policy`

**Files:** Create `migrations/versions/092_atlas_portfolio_policy.py`, test `tests/migrations/test_092_portfolio_policy.py`.

- [ ] **Step 1:** failing test — table `atlas_portfolio_policy` exists with all Policy columns + a partial unique index on `is_house_default WHERE is_house_default`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** write migration 092. Columns mirror the spec's Policy field table: `portfolio_id` (FK, nullable — null = the house default), `is_house_default bool`, `cash_floor_pct`, `respect_regime_cap`, `max_per_stock_pct`, `max_per_sector_pct`, `max_small_cap_pct`, `min_holdings`, `max_positions`, `buy_states text[]`, `min_within_state_rank`, `min_rs_rank`, `hard_stop_pct`, `state_exit_trim`, `state_exit_full`, `trailing_stop_pct nullable`, `instrument_universe` (CHECK in direct_equity/etf/mutual_fund/mixed), `benchmark`, `rebalance_cadence`, `created_at`, `updated_at`. All percentages `Numeric` not float. `down_revision = "091"`.
- [ ] **Step 4:** apply locally + EC2; run test — PASS.
- [ ] **Step 5:** Commit — `feat(migrations): 092 atlas_portfolio_policy`

### Task 2.2: House-default policy seed

- [ ] **Step 1:** failing test — exactly one `is_house_default` row exists after seeding; re-seeding is idempotent.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** a seed script `scripts/seed_house_policy.py` inserting one defensible house default (cash_floor 5%, max_per_stock 5%, max_per_sector 15%, max_small_cap 30%, min_holdings 15, max_positions 40, buy_states {stage_2a,stage_2b}, min_within_state_rank 0.60, min_rs_rank 0.70, hard_stop −8%, state_exit_trim on stage_3, state_exit_full on stage_4, instrument_universe direct_equity, benchmark Nifty 500, rebalance weekly). ON CONFLICT idempotent.
- [ ] **Step 4:** run script + test — PASS.
- [ ] **Step 5:** Commit — `feat(policy): house-default policy seed`

### Task 2.3: Policy module — effective policy

**Files:** Create `atlas/intelligence/policy/__init__.py`, `policy.py`; test `tests/intelligence/policy/test_policy.py`.

- [ ] **Step 1:** failing test (C6/C7) — `effective_policy(portfolio_id)` = house default with the portfolio's non-null overrides applied; a portfolio with no policy row returns the pure house default; `validate_policy` rejects a policy where `min_holdings > max_positions` or `max_per_stock > max_per_sector`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement `effective_policy` (load default, load override, merge non-null) + `validate_policy` (the consistency assertions). Frozen dataclass `Policy`.
- [ ] **Step 4:** run — PASS.
- [ ] **Step 5:** Commit — `feat(policy): effective-policy resolution + validation`

### Task 2.4: Sector-target derivation

**Files:** Create `atlas/intelligence/policy/targets.py`; test `test_targets.py`.

- [ ] **Step 1:** failing test (C6) — `derive_sector_targets(sector_signals, policy, current_weights, regime_cap)`: a sector with `pct_stage_2 ≥ 0.50` proposes a target = `min(engine_suggested, policy.max_per_sector_pct)`; total proposed targets never exceed `regime_cap`; a sector already at/above target proposes gap 0. Hand-compute one full example in the test and assert exact numbers.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement. Formula: engine-suggested sector weight ∝ `pct_stage_2 × mean_within_state_rank`, normalized, then each capped at `policy.max_per_sector_pct`, then the whole vector scaled so the sum ≤ `regime_cap`. Returns per-sector `{current, target, gap}`.
- [ ] **Step 4:** run — PASS.
- [ ] **Step 5:** Commit — `feat(policy): sector-target derivation — engine signal ∩ policy cap ∩ regime cap`

### Task 2.5: Policy config UI surface

**Files:** Create `frontend/src/lib/queries/policy.ts`, `frontend/src/components/portfolio/PolicyPanel.tsx`; modify `frontend/src/app/portfolios/[id]/page.tsx`.

- [ ] **Step 1:** failing test — `PolicyPanel` renders every Policy field grouped (Deployment/Concentration/Entry/Exit/Instrument/Benchmark); each field has a `MetricTooltip` (C3); fields inheriting the house default show an "inherited" marker, overridden fields show "overridden".
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement `policy.ts` query (reads effective policy) + `PolicyPanel` (read-only display first — editing is a follow-up; the panel shows the active policy for the portfolio with inherited/overridden provenance, satisfying C5: real values, no fakes). Wire into the portfolio detail page.
- [ ] **Step 4:** run — PASS. Build + deploy.
- [ ] **Step 5:** Commit — `feat(policy): policy panel on portfolio detail`

### Task 2.6: Recommendations read the Policy

- [ ] **Step 1:** failing test — `/stocks` in flow mode filters out instruments failing `policy.buy_states` / `min_within_state_rank` / `min_rs_rank`; `/sectors` shows policy-capped targets.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** the stock screener, when an active portfolio + sector filter are set, applies the effective policy's entry rules; the sector page renders `derive_sector_targets` output. Two portfolios with different policies demonstrably yield different candidate lists (the spec's DoD #4) — assert this in the test.
- [ ] **Step 4:** run — PASS. Build + deploy.
- [ ] **Step 5:** Commit — `feat(policy): recommendations constrained by effective policy`

---

## WAVE 3 — The Act loop

### Task 3.1: Migration 093 — portfolio target/holding columns

- [ ] **Step 1:** failing test — portfolio holding rows carry `current_weight` + `target_weight`; a `proposed_change` table exists (portfolio_id, instrument_id, proposed_weight, status pending/applied/rejected, created_at).
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** migration 093 — add `target_weight Numeric` to the holdings table, create `atlas_portfolio_proposed_change`. `down_revision = "092"`.
- [ ] **Step 4:** apply + test — PASS.
- [ ] **Step 5:** Commit — `feat(migrations): 093 portfolio targets + proposed changes`

### Task 3.2: Position-sizing formula

**Files:** Create `atlas/intelligence/policy/sizing.py`; test `test_sizing.py`.

- [ ] **Step 1:** failing test (C6) — `suggest_position_size(target_gap, max_per_stock, regime_cap, current_invested)` returns `min(target_gap, max_per_stock, regime_cap − current_invested)`, never negative, clamped to 0 when the book is at the regime cap. Hand-compute 3 cases (gap-bound, stock-cap-bound, regime-cap-bound) and assert exact.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement — pure function, Decimal math.
- [ ] **Step 4:** run — PASS.
- [ ] **Step 5:** Commit — `feat(policy): position-sizing formula`

### Task 3.3: Policy-compliance check

**Files:** Create `atlas/intelligence/policy/compliance.py`; test `test_compliance.py`.

- [ ] **Step 1:** failing test (C7) — `check_compliance(holdings, policy)` returns a list of breaches; a book with a 7% single stock against a 5% cap reports exactly one `max_per_stock` breach; a book at 12 holdings against `min_holdings 15` reports an under-diversified breach; a compliant book returns `[]`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement — evaluate every Policy constraint against the holdings vector, return structured breaches.
- [ ] **Step 4:** run — PASS.
- [ ] **Step 5:** Commit — `feat(policy): policy-compliance check`

### Task 3.4: "Act" affordance on stock detail

**Files:** Create `frontend/src/components/portfolio/ActButton.tsx`; modify `frontend/src/app/stocks/[symbol]/page.tsx`; an API route `frontend/src/app/api/portfolio/propose/route.ts`.

- [ ] **Step 1:** failing test — `ActButton` shows the policy-sized suggestion ("suggest 2.5% — gap-bound") computed from `suggest_position_size`; clicking writes a `pending` row to `atlas_portfolio_proposed_change`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement `ActButton` (reads the active portfolio + effective policy + the sector target gap, shows the sized suggestion with which constraint bound it — C3 explanation) + the propose API route. C5: the suggestion is computed, never a placeholder.
- [ ] **Step 4:** run — PASS. Build + deploy.
- [ ] **Step 5:** Commit — `feat(act): policy-sized Act affordance on stock detail`

### Task 3.5: Portfolio current-vs-target + compliance display

**Files:** Create `frontend/src/components/portfolio/CurrentVsTarget.tsx`; modify the portfolio detail page.

- [ ] **Step 1:** failing test — `CurrentVsTarget` renders each holding's current vs target weight + the gap; pending proposed changes appear as a distinct row; any compliance breach renders a flagged banner. (C7: weights-sum assertion in the test.)
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement — reads holdings + targets + proposed changes + `check_compliance`, renders the table with the breach banner.
- [ ] **Step 4:** run — PASS. Build + deploy.
- [ ] **Step 5:** Commit — `feat(act): portfolio current-vs-target + compliance banner`

### Task 3.6: Deterioration surfacing

**Files:** Create `frontend/src/components/portfolio/DeteriorationPanel.tsx`; modify portfolio detail page + the regime page worklist.

- [ ] **Step 1:** failing test (C7) — a holding hitting `hard_stop_pct` or in `state_exit_full` state surfaces in `DeteriorationPanel`; a healthy holding does not; a holding can't appear as both a buy candidate and a deterioration item.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3:** implement — evaluate each holding against the Policy exit rules, list the ones that breach with the reason, each linked to its stock detail. Feed the count into the regime worklist's "N deteriorating".
- [ ] **Step 4:** run — PASS. Build + deploy.
- [ ] **Step 5:** Commit — `feat(act): deterioration surfacing from policy exit rules`

---

## Self-review

**Spec coverage:** core model (Tasks 2.3-2.6, 3.2-3.6) ✓; Policy field table (2.1) ✓; 6-step flow — step 1 (1.3-1.4), step 2 (2.4, 2.6), step 3 (1.7, 2.6), step 4 (1.5), step 5 (3.2-3.5), step 6 (3.6) ✓; ETF/fund two-tier ranking — verdict label exists today, in-flow rank (2.6) ✓; regime page non-removal (1.3 explicitly merges, removes nothing) ✓; data-model additions (2.1, 3.1) ✓; interactivity 64-element map (1.4-1.6) ✓; 3-wave phasing ✓.

**Placeholder scan:** the repetitive cross-link tasks (1.5, 1.6) describe the swap pattern rather than repeating full code — acceptable because Task 1.1 defines the primitives in full and the pattern is "replace token X with `<LinkedY>`"; the engineer has the components. No TBDs.

**Type consistency:** `Policy` dataclass (2.3) consumed by 2.4/3.2/3.3/3.4 — same field names as migration 092. `effective_policy` / `derive_sector_targets` / `suggest_position_size` / `check_compliance` signatures consistent across their consumers.

**Cross-cutting C1-C7:** baked into each task's steps, not a separate section. Reviewers verify per task.
