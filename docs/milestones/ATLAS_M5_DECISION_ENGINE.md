# Atlas-M5 — Decision Engine

**Document:** ATLAS_M5_DECISION_ENGINE
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Builder:** Claude Code (intended executor)
**References:**
- `00_METHODOLOGY_LOCK.md` (Section 13 — decision engine)
- `01_BACKEND_ARCHITECTURE.md` (Section 5.6 threshold discipline; Section 5.3 pipeline stages 8–10)
- `02_DATABASE_SCHEMA.md` (Section 5 — decision tables)
- `03_VALIDATION_FRAMEWORK.md` (Tier 4 Category C — decision gate reconstruction)
- `04_THRESHOLD_CATALOG.md` (Section 12 — decision threshold)
- `ATLAS_M2_STOCK_ETF_METRICS.md` (provides stock + ETF states)
- `ATLAS_M3_SECTOR_AND_MARKET.md` (provides sector + regime states)
- `ATLAS_M4_MUTUAL_FUND_LENSES.md` (provides fund three-tuple states)

---

## 1. Goal

Build the decision layer of Atlas. This is what fund managers actually act on — the "is this investable, when to enter, when to exit" outputs that answer the three founding questions of the platform.

Three deliverables:

1. **Stock decisions** — investability flag + entry triggers + exit triggers + position sizing for 750 stocks
2. **ETF decisions** — investability flag (5 gates, no volume gate) + 5 entry/exit triggers
3. **Fund decisions** — weekly recommendation (Recommended/Hold/Reduce/Exit) + 4 exit triggers for ~400 funds

**Top-down gating at decision time.** Decisions evaluate market regime → sector state → stock state in that order. A stock can be Leader-Strong-Accumulation but if market is Risk-Off, it's not investable today. This gating happens at decision time, not at state classification time — states stay accurate; decisions reflect today's actionability.

After this milestone, Atlas v0 backend is feature-complete. Frontend integration begins after M5 sign-off.

---

## 2. Dependencies

### 2.1 Predecessors

All of M2, M3, M4 must be complete and signed off:
- Stock states (M2) for stock decisions
- ETF states (M2) for ETF decisions
- Sector states (M3) for sector gating
- Market regime (M3) for regime gating + deployment multiplier
- Fund states (M4) for fund decisions

### 2.2 Foundation Document Consistency Checks

| Foundation Reference | What M5 Depends On |
|---|---|
| Methodology 13.1 | Investability AND-gate logic: market_gate ∧ sector_gate ∧ strength_gate ∧ direction_gate ∧ risk_gate ∧ volume_gate |
| Methodology 13.2 | Entry triggers: TRANSITION_TRIGGER and BREAKOUT_TRIGGER |
| Methodology 13.3 | Position sizing: base × market_multiplier × risk_multiplier |
| Methodology 13.4 | Six parallel exit triggers with action mapping (FULL_EXIT / PARTIAL_TRIM / HOLD_NO_NEW) |
| Methodology 13.5 | ETF decision adaptation: 5 gates (no volume gate); 5 exit triggers |
| Methodology 13.6 | Fund decision: weekly recommendation logic; 4 exit triggers |
| Schema 5.1 | atlas_stock_decisions_daily — investability + entries + exits + position_size_multiplier |
| Schema 5.2 | atlas_etf_decisions_daily — same structure adapted for ETFs |
| Schema 5.3 | atlas_fund_decisions_daily — fund-specific decision row |
| Threshold Catalog 12 | Decision threshold (entry_breakout_proximity_max_pct) |
| Architecture 5.6 | Decision rules receive thresholds dict |

### 2.3 Required Atlas Tables (Read)

| Table | Used For |
|---|---|
| `atlas_stock_states_daily` | Stock state inputs |
| `atlas_stock_metrics_daily` | Distance from 20-EMA, ATR for exit triggers |
| `atlas_etf_states_daily` | ETF state inputs |
| `atlas_etf_metrics_daily` | ETF metrics for breakout calc |
| `atlas_sector_states_daily` | Sector gating |
| `atlas_market_regime_daily` | Market regime gating + deployment multiplier |
| `atlas_fund_states_daily` | Fund three-tuple states |
| `atlas_fund_metrics_daily` | Fund NAV-derived metrics |
| `atlas_thresholds` | Loaded once per pipeline run |

### 2.4 Required Atlas Tables (Read for Lookback)

For exit triggers that depend on state transitions (e.g., "stock fell from Leader/Strong to Average"), the prior day's states are needed:

| Lookback Source | Used For |
|---|---|
| `atlas_stock_states_daily` (T-1, T-5, T-21) | State transition exits |
| `atlas_market_regime_daily` (T-1) | Regime change detection |

---

## 3. Deliverables

### 3.1 Code Deliverables

```
atlas-backend/atlas/compute/
├── decisions_stock.py         # Stock decision pipeline (Stage 8)
├── decisions_etf.py           # ETF decision pipeline (Stage 9)
├── decisions_fund.py          # Fund decision pipeline (Stage 10)
├── gates.py                   # Investability gates (extends M2's gates.py)
├── triggers_entry.py          # Entry trigger logic
├── triggers_exit.py           # Exit trigger logic
└── position_sizing.py         # Position sizing formula
```

```
atlas-backend/scripts/
├── m5_backfill.py             # Historical backfill for decisions
└── m5_daily.py                # Daily incremental run
```

### 3.2 Database Deliverables

| Table | Expected Rows |
|---|---|
| `atlas_stock_decisions_daily` | ~2.25M (750 stocks × ~3,000 days) |
| `atlas_etf_decisions_daily` | ~250K |
| `atlas_fund_decisions_daily` | ~1.2M (only refreshed weekly per methodology 13.6, but stored daily for query simplicity) |

### 3.3 Validation Deliverables

- `validation_M5_<date>.md` with passing Tier 3 (~150 hand-classified decisions) and Tier 4 (decision gate reconstruction)

---

## 4. Phase A — Stock Investability Gates

### 4.1 Goal

For each (stock, date), determine whether the stock is "investable today" — meeting all six gate conditions per methodology 13.1.

### 4.2 Six Gate Conditions

```python
def compute_investability_gates(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> pl.DataFrame:
    """
    For each (stock, date), evaluate the six investability gates.
    
    All six must be True for investable=TRUE. If any is False, stock is non-investable
    today regardless of state strength.
    
    Per methodology 13.1.
    """
    engine = get_engine()
    
    date_filter = (
        f"BETWEEN '{backfill_start}' AND '{target_date}'"
        if is_backfill
        else f"= '{target_date}'"
    )
    
    query = f"""
    SELECT 
        s.instrument_id,
        s.date,
        s.sector,
        s.tier,
        s.rs_state,
        s.momentum_state,
        s.risk_state,
        s.volume_state,
        s.weinstein_gate_pass,
        ss.sector_state,
        mr.regime_state,
        mr.deployment_multiplier,
        mr.dislocation_active
    FROM atlas.atlas_stock_states_daily s
    LEFT JOIN atlas.atlas_sector_states_daily ss
        ON ss.sector_name = s.sector AND ss.date = s.date
    LEFT JOIN atlas.atlas_market_regime_daily mr
        ON mr.date = s.date
    WHERE s.date {date_filter}
      AND s.rs_state NOT IN ('INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED')
    """
    
    df = pl.read_database(query, engine).to_pandas()
    
    # Gate 1 — Market gate: regime not Risk-Off and not dislocation (methodology 13.2)
    df["market_gate"] = (
        (df["regime_state"] != "Risk-Off") &
        (~df["dislocation_active"].fillna(False))
    )

    # Gate 2 — Sector gate: sector_state ∈ {Overweight, Neutral} (methodology 13.2)
    permitted_sectors = ["Overweight", "Neutral"]
    df["sector_gate"] = df["sector_state"].isin(permitted_sectors)

    # Gate 3 — Strength gate: stock RS in {Leader, Strong, Emerging}
    # Note: methodology 13.2 says {Leader, Strong, Emerging}. Consolidating excluded —
    # it's a "former leader pulling back," not eligible for new entries.
    strength_states = ["Leader", "Strong", "Emerging"]
    df["strength_gate"] = df["rs_state"].isin(strength_states)

    # Gate 4 — Direction gate: momentum in {Accelerating, Improving} (methodology 13.2)
    positive_momentum = ["Accelerating", "Improving"]
    df["direction_gate"] = df["momentum_state"].isin(positive_momentum)

    # Gate 5 — Risk gate: risk_state ∈ {Low, Normal} (methodology 13.2 — positive risk only;
    # Elevated/High/Below Trend all blocked)
    permitted_risk = ["Low", "Normal"]
    df["risk_gate"] = df["risk_state"].isin(permitted_risk)

    # Gate 6 — Volume gate: volume_state ∈ {Accumulation, Steady-Buying} (methodology 13.2 —
    # positive conviction required; Neutral/Distribution/Heavy Distribution all blocked)
    positive_volume = ["Accumulation", "Steady-Buying"]
    df["volume_gate"] = df["volume_state"].isin(positive_volume)
    
    # Investability = ALL gates pass (logical AND)
    df["investable"] = (
        df["market_gate"] & df["sector_gate"] & df["strength_gate"] &
        df["direction_gate"] & df["risk_gate"] & df["volume_gate"]
    )
    
    # Identify which gate failed (for transparency / UI display)
    def first_failing_gate(row):
        if not row["market_gate"]: return "market"
        if not row["sector_gate"]: return "sector"
        if not row["strength_gate"]: return "strength"
        if not row["direction_gate"]: return "direction"
        if not row["risk_gate"]: return "risk"
        if not row["volume_gate"]: return "volume"
        return None
    
    df["gating_factor"] = df.apply(first_failing_gate, axis=1)
    
    return pl.from_pandas(df)
```

**Important — gates are AND not OR.** A stock that's Leader RS, Improving momentum, Low risk, Accumulation volume in a Cautious market with Overweight sector is investable. A stock with the same characteristics in Risk-Off market is NOT investable today regardless of how strong its individual states are. Top-down gating means market regime and sector veto stock-level strength.

### 4.3 Phase A Definition of Done

- [ ] Investability gates computed for all (stock, date) combinations in scope
- [ ] `investable` flag is boolean
- [ ] `gating_factor` column populated for non-investable rows (which gate failed first)
- [ ] All six gate columns persisted (for transparency in UI)

---

## 5. Phase B — Entry Triggers

### 5.1 Goal

For each investable stock, determine whether an entry trigger fires today. Two entry trigger types per methodology 13.2.

### 5.2 TRANSITION_TRIGGER

Per methodology 13.3: fires when a stock's **RS momentum** transitions from a weak set
{Flat, Deteriorating} to a strong set {Improving, Accelerating} within the trailing
5 trading days, with `volume_state = Accumulation` confirming the move.

This is a momentum-level trigger, not a state-level transition. The signal is
"strength is turning," caught at the momentum primitive (which leads RS state changes
by days).

```python
def compute_transition_triggers(
    target_date: date,
    is_backfill: bool = False,
) -> pl.DataFrame:
    """
    TRANSITION_TRIGGER fires when:
    - Today: stock is investable (all 6 gates pass)
    - Today: rs_momentum ∈ {Improving, Accelerating}
    - Within the last 5 trading days: rs_momentum was at some point ∈ {Flat, Deteriorating}
    - Today: volume_state = Accumulation

    Per methodology 13.3.
    """
    engine = get_engine()

    # Pull today's state + decisions
    query_today = f"""
        SELECT s.instrument_id, s.momentum_state, s.volume_state, d.investable
        FROM atlas.atlas_stock_states_daily s
        LEFT JOIN atlas.atlas_stock_decisions_daily d
            ON d.instrument_id = s.instrument_id AND d.date = s.date
        WHERE s.date = '{target_date}'
    """

    # Pull last 5 trading days' momentum_state per instrument
    query_recent = f"""
        SELECT instrument_id, date, momentum_state
        FROM atlas.atlas_stock_states_daily
        WHERE date BETWEEN
            (SELECT date FROM atlas.atlas_stock_states_daily
             WHERE date < '{target_date}'
             GROUP BY date ORDER BY date DESC OFFSET 4 LIMIT 1)
            AND '{target_date}'
    """

    today_df = pl.read_database(query_today, engine).to_pandas()
    recent_df = pl.read_database(query_recent, engine).to_pandas()

    weak_set = {"Flat", "Deteriorating"}
    strong_set = {"Improving", "Accelerating"}

    # For each instrument, did momentum_state hit the weak set within the last 5 days?
    weak_in_window = (
        recent_df.groupby("instrument_id")["momentum_state"]
        .apply(lambda s: any(v in weak_set for v in s))
        .rename("had_weak_recently")
        .reset_index()
    )

    merged = today_df.merge(weak_in_window, on="instrument_id", how="left")
    merged["had_weak_recently"] = merged["had_weak_recently"].fillna(False)

    merged["momentum_strong_today"] = merged["momentum_state"].isin(list(strong_set))
    merged["volume_accumulation"] = merged["volume_state"] == "Accumulation"

    merged["transition_trigger_fired"] = (
        merged["investable"].fillna(False)
        & merged["momentum_strong_today"]
        & merged["had_weak_recently"]
        & merged["volume_accumulation"]
    )

    return pl.from_pandas(merged[[
        "instrument_id", "momentum_strong_today", "had_weak_recently",
        "volume_accumulation", "transition_trigger_fired"
    ]])
```

### 5.3 BREAKOUT_TRIGGER

Per methodology 13.3: fires when a stock breaks out to a new 63-day closing high
on accumulation volume, **and** is close enough to the 20-EMA that the entry is a
sane retest rather than chasing an extended move.

```python
def compute_breakout_triggers(
    target_date: date,
    thresholds: dict,
) -> pl.DataFrame:
    """
    BREAKOUT_TRIGGER fires when:
    - Stock is investable today (all 6 gates pass)
    - close > max(close, last 63 trading days) — true 63-day high
    - volume_state = Accumulation
    - |close - ema_20| / ema_20 ≤ entry_breakout_proximity_max_pct (default 5%)

    Per methodology 13.3. Threshold-driven per architecture 5.6.
    """
    PROXIMITY_MAX = thresholds["entry_breakout_proximity_max_pct"] / 100  # default 0.05

    engine = get_engine()

    query = f"""
    WITH today_data AS (
        SELECT
            m.instrument_id,
            m.close,
            m.ema_20_stock,
            s.volume_state,
            d.investable
        FROM atlas.atlas_stock_metrics_daily m
        LEFT JOIN atlas.atlas_stock_states_daily s
            ON s.instrument_id = m.instrument_id AND s.date = m.date
        LEFT JOIN atlas.atlas_stock_decisions_daily d
            ON d.instrument_id = m.instrument_id AND d.date = m.date
        WHERE m.date = '{target_date}'
    ),
    rolling_high AS (
        SELECT
            instrument_id,
            MAX(close) AS high_63d
        FROM atlas.atlas_stock_metrics_daily
        WHERE date BETWEEN
            (SELECT date FROM atlas.atlas_stock_metrics_daily
             WHERE date < '{target_date}'
             GROUP BY date ORDER BY date DESC OFFSET 62 LIMIT 1)
            AND '{target_date}'
        GROUP BY instrument_id
    )
    SELECT t.*, r.high_63d
    FROM today_data t
    LEFT JOIN rolling_high r ON r.instrument_id = t.instrument_id
    """

    df = pl.read_database(query, engine).to_pandas()

    # Distance from 20-EMA (absolute proportion)
    df["distance_from_ema_20"] = (df["close"] - df["ema_20_stock"]).abs() / df["ema_20_stock"]

    df["near_ema_20"] = df["distance_from_ema_20"] <= PROXIMITY_MAX
    df["new_63d_high"] = df["close"] >= df["high_63d"]
    df["volume_accumulation"] = df["volume_state"] == "Accumulation"

    df["breakout_trigger_fired"] = (
        df["investable"].fillna(False)
        & df["new_63d_high"]
        & df["volume_accumulation"]
        & df["near_ema_20"]
    )

    return pl.from_pandas(df[[
        "instrument_id", "new_63d_high", "volume_accumulation",
        "near_ema_20", "distance_from_ema_20", "breakout_trigger_fired"
    ]])
```

**Note on the proximity gate.** A 63-day breakout that's already extended >5% past
the 20-EMA is "chasing." Methodology 13.3 requires the entry to be on a retest of
the 20-EMA — close to the moving average, not far above it. The proximity gate
filters those out.

### 5.4 Phase B Definition of Done

- [ ] Both entry triggers computed for every investable stock
- [ ] `transition_trigger_fired` and `breakout_trigger_fired` columns boolean
- [ ] Triggers only fire when stock is investable (gated by `investable` flag)

---

## 6. Phase C — Position Sizing

### 6.1 Goal

For each stock with an entry trigger fired, compute the position size multiplier per methodology 13.3.

### 6.2 Position Sizing Formula

```python
def compute_position_size(
    decisions_df: pl.DataFrame,
    base_position_size_pct: float = 1.0,  # User-configurable in UI; not a threshold
) -> pl.DataFrame:
    """
    position_size = base_position_size × market_multiplier × risk_multiplier
    
    market_multiplier comes from atlas_market_regime_daily.deployment_multiplier:
        Risk-On=1.0, Constructive=0.7, Cautious=0.4, Risk-Off=0.0
    
    risk_multiplier comes from stock's risk_state (per methodology 13.3):
        Low=1.2, Normal=1.0, Elevated=0.6, High=0.0, Below Trend=0.0

    Note: base_position_size is set by the fund manager (not a threshold) — typically
    represents the "full position" size as % of AUM. v0 default = 1.0% of AUM per name.
    Risk-state Low gets a 1.2x boost — methodology rewards demonstrably-low-risk names
    with a slightly larger position.
    """
    df = decisions_df.to_pandas()

    risk_multiplier_map = {
        "Low": 1.2,
        "Normal": 1.0,
        "Elevated": 0.6,
        "High": 0.0,
        "Below Trend": 0.0,
    }
    
    df["market_multiplier"] = df["deployment_multiplier"]  # From regime
    df["risk_multiplier"] = df["risk_state"].map(risk_multiplier_map).fillna(0.0)
    
    df["position_size_multiplier"] = (
        df["market_multiplier"] * df["risk_multiplier"]
    )
    df["position_size_pct"] = base_position_size_pct * df["position_size_multiplier"]
    
    return pl.from_pandas(df)
```

**Notes:**
- A stock with risk_state=High gets position_size = 0.0% (effectively blocks the entry even though investability gates passed). This is intentional — risk_state=High means "Avoid Entry" per methodology 7.3.
- During Risk-Off regime, market_multiplier = 0.0, so all new positions are 0%. Existing positions still get exit triggers; just no new entries.

### 6.3 Phase C Definition of Done

- [ ] position_size_multiplier computed for every (stock, date)
- [ ] Risk_multiplier mapping verified for all 5 risk states
- [ ] Market_multiplier matches deployment_multiplier from market regime

---

## 7. Phase D — Exit Triggers

### 7.1 Goal

Compute six parallel exit triggers per methodology 13.4. Multiple triggers can fire on
the same day; the trigger that fires determines what happens to freed capital.

### 7.2 The Six Exit Triggers (per methodology 13.4)

| # | Trigger | Condition | Capital Action |
|---|---|---|---|
| 1 | MARKET_RISK_OFF | `market.regime_state` → Risk-Off | Raise to cash (FULL_EXIT) |
| 2 | SECTOR_AVOID | `sector_state` → Avoid | Rotate to other eligible sectors |
| 3 | RS_WEAKEN | `rs_state` ∈ {Average, Weak, Laggard} | Rotate within sector |
| 4 | MOMENTUM_COLLAPSE | `rs_momentum_state` = Collapsing | Rotate within sector |
| 5 | VOLUME_HEAVY_DIST | `volume_state` = Heavy Distribution | Rotate within sector |
| 6 | ATR_STOP | `close < entry_price − 3 × ATR(21)` | Stock-specific stop loss; rotate within sector |

A separate **DISLOCATION** override (per methodology 11.5) suspends all classifications
system-wide; when dislocation is active, all open positions are flat-to-cash. This is a
regime-level pre-emption, not a sixth exit trigger; it short-circuits all of 1–6.

```python
def compute_exit_triggers(
    target_date: date,
    is_backfill: bool = False,
) -> pl.DataFrame:
    """
    Six parallel exit triggers per methodology 13.4. Plus dislocation pre-emption
    per methodology 11.5.

    Triggers:
      1. MARKET_RISK_OFF  — regime_state == Risk-Off                  → FULL_EXIT
      2. SECTOR_AVOID     — sector_state == Avoid                     → ROTATE_OUT_SECTOR
      3. RS_WEAKEN        — rs_state ∈ {Average, Weak, Laggard}       → ROTATE_WITHIN_SECTOR
      4. MOMENTUM_COLLAPSE — rs_momentum_state == Collapsing           → ROTATE_WITHIN_SECTOR
      5. VOLUME_HEAVY_DIST — volume_state == Heavy Distribution        → ROTATE_WITHIN_SECTOR
      6. ATR_STOP         — close < entry_price - 3*ATR(21)           → STOP_LOSS

    Dislocation override (regime-level): when dislocation_active, all positions exit.

    ATR_STOP requires the position's entry_price, which lives in the user's portfolio
    state (not in atlas_*). v0 reads from a portfolio-positions table or from the
    serving layer's session — see Section 7.3 below.
    """
    engine = get_engine()

    today_query = f"""
        SELECT
            s.instrument_id, s.date, s.rs_state, s.momentum_state,
            s.risk_state, s.volume_state, s.sector,
            ss.sector_state,
            mr.regime_state, mr.dislocation_active,
            m.close, m.atr_21
        FROM atlas.atlas_stock_states_daily s
        LEFT JOIN atlas.atlas_stock_metrics_daily m
            ON m.instrument_id = s.instrument_id AND m.date = s.date
        LEFT JOIN atlas.atlas_sector_states_daily ss
            ON ss.sector_name = s.sector AND ss.date = s.date
        LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = s.date
        WHERE s.date = '{target_date}'
    """

    df = pl.read_database(today_query, engine).to_pandas()

    # Trigger 1: MARKET_RISK_OFF
    df["exit_market_risk_off"] = df["regime_state"] == "Risk-Off"

    # Trigger 2: SECTOR_AVOID
    df["exit_sector_avoid"] = df["sector_state"] == "Avoid"

    # Trigger 3: RS_WEAKEN
    weak_rs = ["Average", "Weak", "Laggard"]
    df["exit_rs_weaken"] = df["rs_state"].isin(weak_rs)

    # Trigger 4: MOMENTUM_COLLAPSE
    df["exit_momentum_collapse"] = df["momentum_state"] == "Collapsing"

    # Trigger 5: VOLUME_HEAVY_DIST
    df["exit_volume_heavy_dist"] = df["volume_state"] == "Heavy Distribution"

    # Trigger 6: ATR_STOP — requires entry_price from portfolio table
    # See Section 7.3 — joined in by the caller; here we leave the column NULL when no position
    if "entry_price" in df.columns:
        df["atr_stop_level"] = df["entry_price"] - 3 * df["atr_21"]
        df["exit_atr_stop"] = df["close"] < df["atr_stop_level"]
    else:
        df["atr_stop_level"] = None
        df["exit_atr_stop"] = False

    # Dislocation override (regime-level pre-emption per methodology 11.5)
    df["dislocation_override"] = df["dislocation_active"].fillna(False)

    # Action priority: dislocation > FULL_EXIT > sector rotation > stock rotation > stop loss
    def determine_exit_action(row):
        if row["dislocation_override"]:
            return "DISLOCATION_FULL_EXIT"
        if row["exit_market_risk_off"]:
            return "FULL_EXIT"
        if row["exit_sector_avoid"]:
            return "ROTATE_OUT_SECTOR"
        if row["exit_rs_weaken"]:
            return "ROTATE_WITHIN_SECTOR"
        if row["exit_momentum_collapse"]:
            return "ROTATE_WITHIN_SECTOR"
        if row["exit_volume_heavy_dist"]:
            return "ROTATE_WITHIN_SECTOR"
        if row["exit_atr_stop"]:
            return "STOP_LOSS"
        return None  # No exit fires

    df["exit_action"] = df.apply(determine_exit_action, axis=1)

    df["exit_trigger_fired"] = (
        df["exit_market_risk_off"] | df["exit_sector_avoid"] | df["exit_rs_weaken"]
        | df["exit_momentum_collapse"] | df["exit_volume_heavy_dist"] | df["exit_atr_stop"]
        | df["dislocation_override"]
    )

    merged = df  # keep variable name for the rest of the section

    
    # Any trigger fired (boolean for indexing)
    return pl.from_pandas(merged)
```

**Action priority:** dislocation > FULL_EXIT > ROTATE_OUT_SECTOR > ROTATE_WITHIN_SECTOR
> STOP_LOSS. The UI should show all triggers that fired (for transparency); the
`exit_action` column captures the highest-priority action that maps to capital movement.

**Note on the ATR stop trigger.** Triggers 1–5 are all observable from atlas's own state
tables. Trigger 6 (ATR stop) needs `entry_price` per held position — that's portfolio
state, not market state. Three options for v0:

- **A) Portfolio table.** Maintain `atlas_portfolio_positions` (mstar_id/instrument_id,
  entry_date, entry_price, position_size_pct). Decisions pipeline reads this; ATR stop
  fires per held position. Adds a write path the methodology hadn't called out.
- **B) Compute "would-trigger" universally.** For every stock in atlas_stock_metrics_daily,
  compute the price level X = close − 3 × ATR(21). Surface in UI as "stop level if
  bought today." User-side overlay applies it against their entry price.
- **C) Defer to v1.** Skip the ATR stop in v0 backend; surface ATR(21) as a metric only.

v0 default: **B**. We compute the stop level at the *current price*, surface ATR(21) on
the metrics row, and the UI applies the stop against the user's entered position. No
portfolio-state writes from atlas. Documented as a v1 enhancement to make ATR stops
fully automatic via portfolio-table integration.

### 7.3 Phase D Definition of Done

- [ ] All six exit triggers computed (trigger 6 surfaced as a price-level overlay per
      Section 7.2 note)
- [ ] Each trigger column is boolean
- [ ] `exit_action` ∈ {DISLOCATION_FULL_EXIT, FULL_EXIT, ROTATE_OUT_SECTOR,
      ROTATE_WITHIN_SECTOR, STOP_LOSS, NULL}
- [ ] `exit_trigger_fired` is OR of all six trigger flags + dislocation_override
- [ ] `atr_21` populated in `atlas_stock_metrics_daily` (added to M2 schema; this is the
      input to trigger 6)

---

## 8. Phase E — ETF Decision Adaptations

### 8.1 Goal

Apply ETF-specific decision logic per methodology 13.5: 5 investability gates (no volume gate), 5 exit triggers (no volume_deterioration trigger).

### 8.2 ETF Investability Gates (5 gates, no volume)

```python
def compute_etf_investability_gates(
    target_date: date,
) -> pl.DataFrame:
    """
    ETF investability per methodology 13.5: 5 gates instead of 6.
    Volume gate is dropped (ETF volume is NAV-creation activity, doesn't reflect buyer/seller imbalance).
    
    Theme-conditional sector gating:
    - Broad ETFs (Nifty 50/100/500, etc.): sector gate auto-passes (no single sector exposure)
    - Sectoral ETFs: linked to sector_state via atlas_universe_etfs.linked_sector
    - Thematic ETFs: sector gate uses dominant_sector_state — looked up from de_etf_holdings 
      (largest underlying holding's sector_state)
    """
    engine = get_engine()
    
    # First, compute dominant sector state for thematic ETFs from latest holdings
    # Reads de_etf_holdings (Layer 1) joined to stock universe and sector states
    thematic_dominant_sectors = pl.read_database(f"""
        WITH latest_holdings AS (
            SELECT 
                ticker,
                MAX(as_of_date) AS as_of_date
            FROM public.de_etf_holdings
            WHERE as_of_date <= '{target_date}'
            GROUP BY ticker
        ),
        holdings_with_sector AS (
            SELECT 
                h.ticker,
                h.as_of_date,
                h.weight,
                u.sector
            FROM public.de_etf_holdings h
            JOIN latest_holdings lh 
                ON lh.ticker = h.ticker AND lh.as_of_date = h.as_of_date
            LEFT JOIN atlas.atlas_universe_stocks u 
                ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
            WHERE u.sector IS NOT NULL
        ),
        sector_weights AS (
            -- Aggregate holdings to sector level: sum of weights per sector per ETF
            SELECT 
                ticker,
                as_of_date,
                sector,
                SUM(weight) AS sector_weight
            FROM holdings_with_sector
            GROUP BY ticker, as_of_date, sector
        ),
        ranked_sectors AS (
            -- Rank sectors within each ETF by weight, take the largest
            SELECT 
                ticker,
                as_of_date,
                sector,
                sector_weight,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY sector_weight DESC) AS rn
            FROM sector_weights
        )
        SELECT 
            rs.ticker,
            rs.sector AS dominant_sector,
            rs.sector_weight AS dominant_sector_weight,
            ss.sector_state AS dominant_sector_state
        FROM ranked_sectors rs
        LEFT JOIN atlas.atlas_sector_states_daily ss
            ON ss.sector_name = rs.sector
            AND ss.date = (
                SELECT MAX(date) FROM atlas.atlas_sector_states_daily 
                WHERE date <= '{target_date}'
            )
        WHERE rs.rn = 1
    """, engine)
    
    # Main investability query
    query = f"""
    SELECT 
        e.ticker,
        e.theme,
        e.linked_sector,
        es.rs_state,
        es.momentum_state,
        es.risk_state,
        ss_linked.sector_state AS linked_sector_state,
        mr.regime_state,
        mr.deployment_multiplier,
        mr.dislocation_active
    FROM atlas.atlas_universe_etfs e
    JOIN atlas.atlas_etf_states_daily es 
        ON es.ticker = e.ticker AND es.date = '{target_date}'
    LEFT JOIN atlas.atlas_sector_states_daily ss_linked
        ON ss_linked.sector_name = e.linked_sector AND ss_linked.date = '{target_date}'
    LEFT JOIN atlas.atlas_market_regime_daily mr
        ON mr.date = '{target_date}'
    WHERE e.effective_to IS NULL
      AND es.rs_state NOT IN ('INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED')
    """
    
    df = pl.read_database(query, engine)
    
    # Join in thematic dominant sector data (only relevant for thematic ETFs)
    df = df.join(thematic_dominant_sectors, on="ticker", how="left").to_pandas()
    
    # Gate 1: Market gate
    df["market_gate"] = (
        (df["regime_state"] != "Risk-Off") & 
        (~df["dislocation_active"].fillna(False))
    )
    
    # Gate 2: Sector gate — theme-conditional
    def sector_gate_logic(row):
        if row["theme"] == "Broad":
            # Broad ETFs hold across many sectors — no single-sector exposure to gate
            return True
        elif row["theme"] == "Sectoral":
            # Sectoral ETFs: gated by their linked sector's state
            return row.get("linked_sector_state") not in ["Avoid", None]
        elif row["theme"] == "Thematic":
            # Thematic ETFs: gated by their dominant holding sector's state
            # If no holdings data available (e.g., new ETF), fall back to auto-pass with logged warning
            if pd.isna(row.get("dominant_sector_state")):
                return True  # Fallback — log this in run_log for review
            return row["dominant_sector_state"] not in ["Avoid"]
        return False
    
    df["sector_gate"] = df.apply(sector_gate_logic, axis=1)
    
    # Gate 3: Strength gate
    df["strength_gate"] = df["rs_state"].isin(["Leader", "Strong", "Consolidating", "Emerging"])
    
    # Gate 4: Direction gate
    df["direction_gate"] = df["momentum_state"].isin(["Accelerating", "Improving"])
    
    # Gate 5: Risk gate
    df["risk_gate"] = ~df["risk_state"].isin(["High", "Below Trend"])
    
    # No volume gate
    
    df["investable"] = (
        df["market_gate"] & df["sector_gate"] & df["strength_gate"] &
        df["direction_gate"] & df["risk_gate"]
    )
    
    return pl.from_pandas(df)
```

**Implementation notes:**

1. **Dominant sector lookup** uses the latest available holdings disclosure on or before the target date. If an ETF's holdings haven't been disclosed yet (newly added thematic ETFs), the sector gate falls back to auto-pass with a warning logged in `atlas_run_log`. Validation Tier 4 surfaces ETFs falling back to ensure this doesn't silently mask real issues.

2. **Sector aggregation from holdings** sums constituent weights per sector. The "dominant" sector is the one with the largest aggregated weight. For tightly thematic ETFs (e.g., a Consumer Discretionary thematic ETF), one sector typically dominates >40-50% of the ETF. For broader thematic ETFs (e.g., ESG or "next-gen India" themes), no sector may dominate clearly — in those cases, the gate uses the largest sector by weight regardless.

3. **Thematic ETFs with `unknown` or unmapped underlying holdings** — if a thematic ETF holds stocks not in `atlas_universe_stocks` (international or smaller names), those holdings don't contribute to sector aggregation. As long as enough mapped holdings exist to identify a dominant sector, the gate operates correctly. ETFs where >50% of AUM is unmapped are flagged for review.

### 8.3 ETF Entry and Exit Triggers

ETF entry triggers identical to stocks (TRANSITION + BREAKOUT). Exit triggers: 5 instead of 6 (drop VOLUME_DETERIORATION).

ETF position sizing identical formula: base × market_multiplier × risk_multiplier.

### 8.4 Phase E Definition of Done

- [ ] ETF investability uses 5 gates
- [ ] Sectoral ETFs gated by their linked sector state
- [ ] Broad ETFs auto-pass sector gate (no single sector exposure)
- [ ] Thematic ETFs gated by dominant sector state (computed from `de_etf_holdings`)
- [ ] Thematic ETFs without holdings data fall back to auto-pass with warning logged
- [ ] 5 exit triggers (no volume deterioration)

---

## 9. Phase F — Fund Decisions

### 9.1 Goal

Per methodology 13.6: weekly recommendation logic + 4 exit triggers for fund holdings.

### 9.2 Weekly Recommendation Classification

```python
def compute_fund_recommendation(
    target_date: date,
    thresholds: dict,
) -> pl.DataFrame:
    """
    Weekly fund recommendation per methodology 13.6.
    
    Recommendation depends on the three-tuple (nav_state, composition_state, holdings_state):
    - Recommended: nav_state ∈ {Leader NAV, Strong NAV} AND composition = Aligned AND holdings = Strong-Holdings
    - Hold: nav_state ∈ {Leader NAV, Strong NAV, Average NAV} AND not all three lenses positive
    - Reduce: nav_state ∈ {Weak NAV} OR (composition = Misaligned AND holdings = Weak-Holdings)
    - Exit: nav_state = Laggard NAV OR market regime = Risk-Off
    """
    engine = get_engine()
    
    query = f"""
    SELECT 
        fs.mstar_id,
        fs.date,
        fs.nav_state,
        fs.composition_state,
        fs.holdings_state,
        mr.regime_state,
        mr.dislocation_active
    FROM atlas.atlas_fund_states_daily fs
    LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = fs.date
    WHERE fs.date = '{target_date}'
    """
    
    df = pl.read_database(query, engine).to_pandas()
    
    nav_strong = ["Leader NAV", "Strong NAV"]
    
    def determine_recommendation(row):
        # Exit trumps everything
        if row["nav_state"] == "Laggard NAV":
            return "Exit"
        if row["regime_state"] == "Risk-Off":
            return "Exit"
        if row["dislocation_active"]:
            return "Exit"
        
        # Reduce signals
        if row["nav_state"] == "Weak NAV":
            return "Reduce"
        if row["composition_state"] == "Misaligned" and row["holdings_state"] == "Weak-Holdings":
            return "Reduce"
        
        # Recommended (best case)
        if (row["nav_state"] in nav_strong and 
            row["composition_state"] == "Aligned" and 
            row["holdings_state"] == "Strong-Holdings"):
            return "Recommended"
        
        # Default: Hold
        return "Hold"
    
    df["fund_recommendation"] = df.apply(determine_recommendation, axis=1)
    
    return pl.from_pandas(df)
```

### 9.3 Fund Exit Triggers

Per methodology 13.6, four parallel fund exit triggers:

```python
def compute_fund_exit_triggers(
    target_date: date,
) -> pl.DataFrame:
    """
    Four fund exit triggers per methodology 13.6:
    1. NAV_DOWNGRADE — nav_state moved from {Leader NAV, Strong NAV} to {Weak NAV, Laggard NAV}
    2. COMPOSITION_MISALIGNED — composition moved to Misaligned
    3. HOLDINGS_WEAKENED — holdings moved to Weak-Holdings
    4. MARKET_RISK_OFF — regime moved to Risk-Off
    """
    # Implementation similar to stock exit triggers — load today + yesterday, detect changes
    # ...
    pass
```

### 9.4 Fund Recommendation Transition Triggers

Beyond the lens-level exit triggers above, fund decisions need **recommendation-level transition triggers** to drive UI signaling and trade actions. The lens-level triggers fire on individual state changes (e.g., "holdings weakened"); the recommendation-level triggers fire when the overall recommendation changes (e.g., "this fund just became Recommended" or "this fund just became Exit").

This is the asymmetric counterpart to stock entry/exit triggers, adapted for funds' weekly cadence:

```python
def compute_fund_recommendation_transitions(
    target_date: date,
) -> pl.DataFrame:
    """
    Compute recommendation-level transition triggers and weeks-in-state.
    
    Compares this week's recommendation to last week's recommendation.
    Fires four boolean triggers based on transition direction.
    """
    engine = get_engine()
    
    # Get last week's recommendation per fund (most recent week prior to target_date)
    last_week_query = f"""
        SELECT mstar_id, fund_recommendation AS last_week_recommendation
        FROM atlas.atlas_fund_decisions_daily
        WHERE date = (
            SELECT MAX(date) FROM atlas.atlas_fund_decisions_daily 
            WHERE date < '{target_date}'
        )
    """
    last_week = pl.read_database(last_week_query, engine).to_pandas()
    
    # Get this week's recommendation
    this_week_query = f"""
        SELECT mstar_id, fund_recommendation
        FROM atlas.atlas_fund_decisions_daily
        WHERE date = '{target_date}'
    """
    this_week = pl.read_database(this_week_query, engine).to_pandas()
    
    df = this_week.merge(last_week, on="mstar_id", how="left")
    df["last_week_recommendation"] = df["last_week_recommendation"].fillna("New")
    
    # Four transition triggers:
    # entry_trigger: recommendation became Recommended this week
    df["entry_trigger"] = (
        (df["fund_recommendation"] == "Recommended") &
        (df["last_week_recommendation"] != "Recommended")
    )
    
    # exit_trigger: recommendation became Exit this week
    df["exit_trigger"] = (
        (df["fund_recommendation"] == "Exit") &
        (df["last_week_recommendation"] != "Exit")
    )
    
    # reduce_trigger: recommendation became Reduce this week
    df["reduce_trigger"] = (
        (df["fund_recommendation"] == "Reduce") &
        (df["last_week_recommendation"] != "Reduce")
    )
    
    # add_trigger: recommendation moved upward (Reduce/Hold → Recommended, or Exit → Hold/Reduce)
    # Captures "fund improving" signals beyond just entry into Recommended
    upgrade_pairs = {
        ("Hold", "Recommended"), ("Reduce", "Recommended"), ("Reduce", "Hold"),
        ("Exit", "Reduce"), ("Exit", "Hold"), ("Exit", "Recommended"),
    }
    df["add_trigger"] = df.apply(
        lambda r: (r["last_week_recommendation"], r["fund_recommendation"]) in upgrade_pairs,
        axis=1,
    )
    
    return pl.from_pandas(df)


def compute_weeks_in_current_state(
    target_date: date,
) -> pl.DataFrame:
    """
    For each fund, count consecutive weeks the current recommendation has held.
    
    Useful for distinguishing "newly Recommended (1 week)" from "consistently Recommended 
    (12 weeks)". Both are buy signals but with different conviction levels.
    """
    engine = get_engine()
    
    # Walk backward through weekly decisions, count until recommendation changes
    query = f"""
        WITH weekly_decisions AS (
            -- Distinct weekly recommendations for each fund
            SELECT 
                mstar_id, 
                date, 
                fund_recommendation,
                LAG(fund_recommendation) OVER (PARTITION BY mstar_id ORDER BY date) AS prev_recommendation
            FROM atlas.atlas_fund_decisions_daily
            WHERE date <= '{target_date}'
              AND date > '{target_date}'::date - INTERVAL '2 years'
            -- Filter to one row per week (Monday or first trading day)
            -- (Implementation: filter using a weekly marker column or date arithmetic)
        ),
        change_points AS (
            SELECT 
                mstar_id,
                date,
                fund_recommendation,
                CASE 
                    WHEN prev_recommendation IS DISTINCT FROM fund_recommendation THEN 1 
                    ELSE 0 
                END AS state_changed
            FROM weekly_decisions
        ),
        latest_change AS (
            SELECT 
                mstar_id, 
                MAX(date) AS last_change_date
            FROM change_points
            WHERE state_changed = 1
            GROUP BY mstar_id
        )
        SELECT 
            wd.mstar_id,
            -- Count weeks since last change
            COUNT(*) AS weeks_in_current_state
        FROM weekly_decisions wd
        LEFT JOIN latest_change lc ON lc.mstar_id = wd.mstar_id
        WHERE wd.date >= COALESCE(lc.last_change_date, '2014-01-01')
          AND wd.date <= '{target_date}'
        GROUP BY wd.mstar_id
    """
    
    return pl.read_database(query, engine)
```

**Storage in `atlas_fund_decisions_daily`:**

The four trigger booleans plus `weeks_in_current_state` need columns added to the schema:

```sql
ALTER TABLE atlas.atlas_fund_decisions_daily 
ADD COLUMN entry_trigger          BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN exit_trigger           BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN reduce_trigger         BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN add_trigger            BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN weeks_in_current_state INTEGER,
ADD COLUMN last_week_recommendation VARCHAR(16);
```

These columns must be added to `02_DATABASE_SCHEMA.md` Section 5.3 — to be done as part of M5 build prep.

**UI contract:**

The dashboard's primary view of mutual funds shows the current recommendation distribution (count of Recommended / Hold / Reduce / Exit funds). A secondary "What changed this week" panel filters to funds where any transition trigger fired this week. The `weeks_in_current_state` column drives sort order ("show me newly Recommended funds first") and conviction display ("Recommended for 8 weeks" badge).

**Asymmetric trigger philosophy:**

Same as stocks — exits are easier to fire than entries:
- Any of `exit_trigger` OR `reduce_trigger` firing → trim or close positions
- `entry_trigger` firing alone → consider new position, but combine with `weeks_in_current_state ≥ 4` for higher conviction (newly-Recommended funds may be transient)
- `add_trigger` (upgrade without reaching Recommended) → watchlist signal, not immediate action

### 9.5 Phase F Definition of Done

- [ ] Fund recommendation computed per (fund, date)
- [ ] Four lens-level exit triggers computed
- [ ] Four recommendation-level transition triggers computed (entry, exit, reduce, add)
- [ ] `weeks_in_current_state` populated for every fund-date
- [ ] `last_week_recommendation` populated for transition tracking
- [ ] Recommendation ∈ {Recommended, Hold, Reduce, Exit}
- [ ] Schema migration applied to add the 6 new columns to `atlas_fund_decisions_daily`

---

## 10. Phase G — Pipeline Integration

### 10.1 Daily Run

```python
def run_m5_daily(target_date: date):
    """
    M5 daily pipeline.
    
    Stages 8 (stocks), 9 (ETFs), 10 (funds) per architecture 5.3.
    """
    engine = get_engine()
    thresholds = load_thresholds(engine)
    run_id = uuid.uuid4()
    
    # Stage 8: Stock decisions
    print("Stage 8: Stock decisions...")
    stock_gates = compute_investability_gates(target_date)
    stock_transitions = compute_transition_triggers(target_date)
    stock_breakouts = compute_breakout_triggers(target_date, thresholds)
    stock_exits = compute_exit_triggers(target_date)
    
    # Combine into one dataframe
    stock_decisions = (stock_gates
        .join(stock_transitions, on="instrument_id")
        .join(stock_breakouts, on="instrument_id")
        .join(stock_exits, on="instrument_id")
    )
    stock_decisions = compute_position_size(stock_decisions)
    
    write_to_stock_decisions(engine, stock_decisions, run_id)
    
    # Stage 9: ETF decisions
    print("Stage 9: ETF decisions...")
    etf_gates = compute_etf_investability_gates(target_date)
    # ... entry + exit triggers, position sizing
    
    # Stage 10: Fund decisions
    print("Stage 10: Fund decisions...")
    fund_recommendations = compute_fund_recommendation(target_date, thresholds)
    fund_exits = compute_fund_exit_triggers(target_date)
    
    fund_decisions = fund_recommendations.join(fund_exits, on="mstar_id")
    write_to_fund_decisions(engine, fund_decisions, run_id)
    
    print(f"M5 daily complete for {target_date}")
```

### 10.2 Backfill Strategy

Backfill processes dates sequentially because exit triggers depend on prior-day state. Cannot parallelize across dates.

```python
def run_m5_backfill():
    """
    M5 historical backfill — sequential by date.
    Cannot parallelize: exit triggers need T-1 state.
    """
    start = date(2014, 4, 1)  # Or earliest date with M2/M3/M4 outputs
    end = date.today()
    
    all_dates = load_trading_dates(start, end)
    for d in all_dates:
        run_m5_daily(d)
```

### 10.3 Phase G Definition of Done

- [ ] Daily run script works end-to-end
- [ ] Backfill script populates all three decision tables
- [ ] All M5 runs logged in `atlas_run_log`

---

## 11. Phase H — Validation

### 11.1 Tier 3 — Hand-Classified Decisions

Sample sizes:

- 30 stocks × 1 date = 30 hand-classified investability decisions
- 30 stocks × 1 date = 30 hand-classified entry triggers
- 30 stocks × 1 date = 30 hand-classified exit triggers
- 10 ETFs × 1 date = 10 hand-classified ETF decisions
- 10 funds × 1 date = 10 hand-classified fund recommendations

Hand-classification reads methodology 13 verbatim and translates each rule into a separate independent function.

### 11.2 Tier 4 — Decision Gate Reconstruction

Per validation framework Section 5 Category C:

- For 100 sample (stock, date) rows in `atlas_stock_decisions_daily`, manually reconstruct each gate's truth value from the source state tables. Verify all six gates match exactly.
- For 50 sample fund recommendations, reconstruct from fund three-tuple states + market regime. Verify exact match.

### 11.3 Tier 5 — Three Consecutive Daily Runs

Standard.

### 11.4 Phase H Definition of Done

- [ ] Tier 3: 100% pass on hand-classifications
- [ ] Tier 4: 100% gate reconstruction (zero mismatches)
- [ ] Tier 5: 3 consecutive nightly runs pass
- [ ] `validation_M5_<date>.md` shows PASS

---

## 12. Atlas-M5 Definition of Done

**Code:**
- [ ] All compute modules implemented (decisions_stock.py, decisions_etf.py, decisions_fund.py, gates.py, triggers_entry.py, triggers_exit.py, position_sizing.py)
- [ ] Pipeline scripts working

**Database:**
- [ ] `atlas_stock_decisions_daily`: ~2.25M rows
- [ ] `atlas_etf_decisions_daily`: ~250K rows
- [ ] `atlas_fund_decisions_daily`: ~1.2M rows

**Validation:**
- [ ] Tier 3, 4, 5 all pass
- [ ] `validation_M5_<date>.md` shows PASS

**Sign-off:**
- [ ] Engineer (Claude Code): Build complete
- [ ] Architect (Nimish): Spot-checked validation
- [ ] Fund Manager (Bhaven): Spot-checked 10 stock decisions across investability/entry/exit, agrees with output
- [ ] Atlas v0 backend declared feature-complete

---

## 13. Common Pitfalls

**1. Investability is ALL-AND, not weighted.** Six gates, all must pass. A "very strong" stock with a failing volume gate is NOT investable. Don't try to build a "score" or weighted version. Per methodology 13.1, this is binary — investable or not.

**2. Top-down gating at decision time, not state classification time.** A stock can stay classified Leader during Risk-Off — that's correct. But it's not investable today. States measure what is; decisions measure what's actionable. Don't conflate.

**3. Entry triggers gated by investability.** A stock can transition into Leader but if it doesn't pass all six gates, no trigger fires. Both transition AND breakout require `investable=True`.

**4. Exit triggers fire regardless of investability.** A stock that's no longer investable should still get exit triggers if any of the six conditions fire. Exits are about existing positions; investability is about new positions.

**5. Action priority for exits.** FULL_EXIT > PARTIAL_TRIM > HOLD_NO_NEW. If multiple triggers fire on same day, take the worst action. Show all triggers in UI for transparency.

**6. Position sizing zero-out for High risk.** A stock with risk_state=High gets position_size_multiplier = 0 (via the risk_multiplier map), even if other gates pass. This intentionally blocks the entry — methodology 7.3 says "Avoid Entry" for High risk.

**7. Don't include states in decisions table.** The decisions table stores decision rows (investable, entries, exits, action) — NOT state values. Query joins to atlas_stock_states_daily for state context if needed. Avoid duplicating states.

**8. Sequential backfill required.** Exit triggers depend on T-1 state. M5 backfill runs date-by-date in chronological order. Cannot parallelize across dates.

**9. Fund recommendation refresh cadence.** Methodology 13.6 says "weekly" for fund recommendations. v0 implementation: store daily for query simplicity but recommendations only meaningfully change on weeks where state tuple changes. Document this in validation.

**10. ETF theme-conditional sector gating.** Sectoral ETFs (TECHBEES, BANKBEES, etc.) gated by their linked sector state. Broad ETFs (NIFTYBEES, JUNIORBEES) auto-pass the sector gate (no single sector exposure). Thematic ETFs (consumption, infrastructure, etc.) gated by their **dominant sector state** — looked up by aggregating constituent weights from `de_etf_holdings`, finding the largest-weighted sector, and reading that sector's state from `atlas_sector_states_daily`. Thematic ETFs lacking holdings data (rare — typically only newly-added ETFs) fall back to auto-pass with a logged warning.

---

## 14. Foundation Document Sync Checks

| Check | Documents Involved |
|---|---|
| Six investability gates: market, sector, strength, direction, risk, volume | Methodology 13.1 ↔ Schema 5.1 ↔ M5 Section 4.2 |
| Two entry triggers: TRANSITION_TRIGGER, BREAKOUT_TRIGGER | Methodology 13.2 ↔ Schema 5.1 ↔ M5 Section 5 |
| Six exit triggers; FULL_EXIT/PARTIAL_TRIM/HOLD_NO_NEW action mapping | Methodology 13.4 ↔ Schema 5.1 ↔ M5 Section 7.2 |
| Position sizing: base × market_multiplier × risk_multiplier | Methodology 13.3 ↔ M5 Section 6.2 |
| Risk multiplier values: Low=1.0, Normal=0.85, Elevated=0.6, High=0.0, Below Trend=0.0 | Methodology 13.3 ↔ M5 Section 6.2 |
| ETF: 5 gates (no volume), 5 exit triggers | Methodology 13.5 ↔ Schema 5.2 ↔ M5 Section 8 |
| Fund recommendation: 4 levels (Recommended/Hold/Reduce/Exit) | Methodology 13.6 ↔ Schema 5.3 ↔ M5 Section 9.2 |
| Fund exit triggers: 4 triggers | Methodology 13.6 ↔ Schema 5.3 ↔ M5 Section 9.3 |
| Decision threshold key: entry_breakout_proximity_max_pct | Threshold Catalog 12 ↔ M5 Section 5.3 |
| Top-down gating order: market → sector → stock | Methodology 13.1 ↔ M5 Section 4.2 |

---

## 15. Open Questions

1. **Base position size — fund manager input or default?** Default to 1.0% per name in v0; add UI input later. Document as a fund-manager-controlled parameter (NOT a threshold in atlas_thresholds — fund-specific operational parameter).

2. **Breakout 5-day positive window — calendar or trading days?** Default trading days (5 trading days = ~1 calendar week). Document.

3. **State transition definition for TRANSITION_TRIGGER.** Today vs yesterday is straightforward. But what if a stock oscillates: Leader → Average → Leader within a week? Each transition into Leader fires the trigger. Acceptable v0 behavior — fund manager can decide whether to act on the second signal.

4. **Fund weekly cadence.** v0 stores daily but decisions only update on actual state changes. Should we add a `last_recommendation_change_date` column for clarity? Defer to v1.

---

## 16. What Comes Next — Atlas v0 Feature-Complete

After M5 sign-off, Atlas backend is feature-complete for v0. Next steps:

- Frontend integration (Atlas UI consuming the decision tables)
- Production deployment (cron + monitoring + alerting)
- User acceptance testing with fund manager
- v1 enhancement planning based on usage feedback

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** Atlas-M5 completion → Atlas v0 backend declared complete
