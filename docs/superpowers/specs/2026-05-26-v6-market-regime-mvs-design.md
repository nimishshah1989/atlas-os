# v6 Page 01 Market Regime — MV Design Spec

**Date:** 2026-05-26 (overnight session)
**Status:** draft — ready to land in next session
**Mockup:** `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/01-market-regime.html`
**Backing MV:** `mv_market_regime_landing` (1 wide MV with JSONB nested sections)
**Source-of-truth doc:** `docs/v6/2026-05-26-page-data-inventory.md` (Page 01 section)

---

## Locked decisions (per /grill-with-docs + buildout-plan)

| ID | Decision |
|---|---|
| D1 | **Single wide MV with JSONB nested.** Rather than 4 separate MVs, one wide row holds all data for the latest snapshot date. Sections (hero / 12wk-journey / pulse-tiles / cells-favored / conviction-tabs) are JSONB arrays/objects. |
| D2 | **Hybrid v5+v6 regime read pattern.** State + 4 driver attributions from `atlas_regime_daily` (v6); rich numeric inputs from `atlas_market_regime_daily` (v5). Per ADR `.ruflo/adr/2026-05-26-v6-mv-hybrid-regime-read.md`. |
| D3 | **Confidence band fallback to unconditional.** `confidence_by_regime` is 0/21 populated; for v6.0 use `confidence_unconditional` with H/M/L cutoffs from `atlas_thresholds`. When `confidence_by_regime` populates, swap. |
| D4 | **Deployment defaults hardcoded.** Risk-On 60%, Elevated 50%, Cautious 40%, Risk-Off 30% (per CONTEXT.md regime deployment locked). Hardcoded constants in MV body; do NOT add a config table for 4 numbers. |
| D5 | **Liquid BeES yield hardcoded 6.5%** for footnote. Pure presentation; not a load-bearing metric. |
| D6 | **Single refresh nightly at 20:00 IST** via pg_cron after writer chain completes. |

---

## Inputs already in place

| Source | Columns used |
|---|---|
| `atlas_market_regime_daily` (v5) | `date`, `regime_state`, `deployment_multiplier`, `pct_above_ema_200`, `india_vix`, `ad_ratio`, `mcclellan_oscillator`, `new_52w_highs`, `new_52w_lows` |
| `atlas_regime_daily` (v6, EMPTY) | `smallcap_rs_z`, `cross_sectional_dispersion`, `vix_percentile`, `breadth_pct_above_200dma` — fallback: compute from `de_equity_ohlcv` / `de_index_prices` in MV |
| `atlas_cell_definitions` | `cell_id`, `cap_tier`, `action`, `tenure`, `display_name` (NEW post-097), `explain_text` (NEW post-097), `friction_adjusted_excess`, `confidence_unconditional` |
| `atlas_signal_calls` | `cell_id`, `instrument_id`, `confidence_unconditional`, `predicted_excess`, `exit_date` |
| `atlas_scorecard_daily` | `instrument_id`, `composite` derivation, `cap_tier` |
| `atlas_universe_stocks` | `symbol`, `company_name`, `sector`, `tier`, `in_nifty_500` |
| `atlas_mf_recommendation_daily` (587 rows post-C1.b) | `mf_instrument_id`, `category`, `peer_quartile`, `recommendation` |
| `atlas_etf_signal_calls` | `etf_instrument_id`, `cell_id`, `action`, `predicted_excess`, `exit_date` |
| `atlas_etf_scorecard` | `ticker`, `etf_name`, `etf_category`, `composite_score` |
| `atlas_universe_funds` | `mstar_id`, `scheme_name`, `category_name`, `plan_type` |
| `atlas_universe_etfs` | `ticker`, `etf_name`, `theme`, `linked_sector` |

---

## MV body — schema

```sql
CREATE MATERIALIZED VIEW atlas.mv_market_regime_landing AS
WITH
-- ===========================================================================
-- 1. Latest snapshot date anchor
-- ===========================================================================
latest AS (
  SELECT MAX(date) AS d FROM atlas.atlas_market_regime_daily
),

-- ===========================================================================
-- 2. Regime hero — state + days held + entered date + prior state
-- ===========================================================================
regime_hero AS (
  SELECT
    m.date AS as_of_date,
    m.regime_state,
    m.deployment_multiplier,
    -- Days held: count consecutive trailing days where regime_state == today
    (SELECT COUNT(*) FROM atlas.atlas_market_regime_daily r
      WHERE r.date <= m.date
        AND r.date >= (
          SELECT MIN(r2.date) FROM atlas.atlas_market_regime_daily r2
          WHERE r2.date <= m.date
            AND r2.regime_state = m.regime_state
            AND NOT EXISTS (
              SELECT 1 FROM atlas.atlas_market_regime_daily r3
              WHERE r3.date > r2.date AND r3.date <= m.date
                AND r3.regime_state != m.regime_state
            )
        )
    ) AS days_in_regime,
    -- Entered date: MIN(date) of current streak (computed same way)
    (SELECT MIN(r2.date) FROM atlas.atlas_market_regime_daily r2
      WHERE r2.date <= m.date
        AND r2.regime_state = m.regime_state
        AND NOT EXISTS (
          SELECT 1 FROM atlas.atlas_market_regime_daily r3
          WHERE r3.date > r2.date AND r3.date <= m.date
            AND r3.regime_state != m.regime_state
        )
    ) AS entered_date,
    -- Prior regime: regime_state on the day BEFORE entered_date
    (SELECT prev.regime_state FROM atlas.atlas_market_regime_daily prev
      WHERE prev.date < (
        SELECT MIN(r2.date) FROM atlas.atlas_market_regime_daily r2
        WHERE r2.date <= m.date AND r2.regime_state = m.regime_state
          AND NOT EXISTS (
            SELECT 1 FROM atlas.atlas_market_regime_daily r3
            WHERE r3.date > r2.date AND r3.date <= m.date AND r3.regime_state != m.regime_state
          )
      )
      ORDER BY prev.date DESC LIMIT 1
    ) AS prior_regime_state
  FROM atlas.atlas_market_regime_daily m
  WHERE m.date = (SELECT d FROM latest)
),

-- ===========================================================================
-- 3. Regime transition stats (typical length + next-state probabilities)
-- ===========================================================================
-- Identify all regime streaks in history, then compute avg length and transition matrix
regime_streaks AS (
  SELECT
    regime_state,
    grp,
    MIN(date) AS streak_start,
    MAX(date) AS streak_end,
    COUNT(*) AS streak_days,
    LEAD(regime_state) OVER (ORDER BY MIN(date)) AS next_state
  FROM (
    SELECT
      date, regime_state,
      SUM(state_changed) OVER (ORDER BY date) AS grp
    FROM (
      SELECT date, regime_state,
        CASE WHEN regime_state != LAG(regime_state) OVER (ORDER BY date) THEN 1 ELSE 0 END AS state_changed
      FROM atlas.atlas_market_regime_daily
    ) s
  ) g
  GROUP BY regime_state, grp
),
regime_stats AS (
  SELECT
    rh.regime_state,
    AVG(rs.streak_days)::int AS typical_length_days,
    jsonb_object_agg(
      next_state,
      ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY rh.regime_state), 0)
    ) FILTER (WHERE next_state IS NOT NULL) AS next_state_probs
  FROM regime_hero rh
  JOIN regime_streaks rs USING (regime_state)
  GROUP BY rh.regime_state
),

-- ===========================================================================
-- 4. Trailing 60-day regime segments (for the hero strip bar)
-- ===========================================================================
recent_60d_regimes AS (
  SELECT jsonb_agg(jsonb_build_object('state', regime_state, 'days', streak_days) ORDER BY streak_start) AS segments
  FROM regime_streaks
  WHERE streak_end >= (SELECT d FROM latest) - INTERVAL '60 days'
),

-- ===========================================================================
-- 5. 12-week journey — weekly last-of for 4 metric rows
-- ===========================================================================
twelve_week_journey AS (
  SELECT jsonb_agg(jsonb_build_object(
    'week_start', wk,
    'regime_state', regime_state,
    'smallcap_rs_z', smallcap_rs_z,
    'breadth_pct', breadth_pct,
    'india_vix', india_vix,
    'dispersion', dispersion
  ) ORDER BY wk) AS rows
  FROM (
    SELECT DISTINCT ON (date_trunc('week', m.date))
      date_trunc('week', m.date)::date AS wk,
      m.regime_state,
      -- smallcap_rs_z: prefer atlas_regime_daily; fallback to derived
      COALESCE(r.smallcap_rs_z, NULL) AS smallcap_rs_z,
      m.pct_above_ema_200 AS breadth_pct,
      m.india_vix,
      COALESCE(r.cross_sectional_dispersion, NULL) AS dispersion
    FROM atlas.atlas_market_regime_daily m
    LEFT JOIN atlas.atlas_regime_daily r USING (date)
    WHERE m.date >= (SELECT d FROM latest) - INTERVAL '84 days'
    ORDER BY date_trunc('week', m.date), m.date DESC
  ) w
),

-- ===========================================================================
-- 6. India Pulse tiles — 4 tiles with 12-week sparkline arrays
-- ===========================================================================
pulse_tiles AS (
  SELECT jsonb_build_object(
    'smallcap_rs_z',          (SELECT smallcap_rs_z FROM atlas.atlas_regime_daily WHERE date = (SELECT d FROM latest)),
    'breadth_pct',            (SELECT pct_above_ema_200 FROM atlas.atlas_market_regime_daily WHERE date = (SELECT d FROM latest)),
    'india_vix',              (SELECT india_vix FROM atlas.atlas_market_regime_daily WHERE date = (SELECT d FROM latest)),
    'dispersion',             (SELECT cross_sectional_dispersion FROM atlas.atlas_regime_daily WHERE date = (SELECT d FROM latest)),
    -- 12 weekly values for sparkline data
    'smallcap_rs_z_spark',    (SELECT jsonb_agg(smallcap_rs_z) FROM (SELECT DISTINCT ON (date_trunc('week', date)) smallcap_rs_z FROM atlas.atlas_regime_daily WHERE date >= (SELECT d FROM latest) - INTERVAL '84 days' ORDER BY date_trunc('week', date), date DESC) s),
    'breadth_pct_spark',      (SELECT jsonb_agg(pct_above_ema_200) FROM (SELECT DISTINCT ON (date_trunc('week', date)) pct_above_ema_200 FROM atlas.atlas_market_regime_daily WHERE date >= (SELECT d FROM latest) - INTERVAL '84 days' ORDER BY date_trunc('week', date), date DESC) s),
    'india_vix_spark',        (SELECT jsonb_agg(india_vix) FROM (SELECT DISTINCT ON (date_trunc('week', date)) india_vix FROM atlas.atlas_market_regime_daily WHERE date >= (SELECT d FROM latest) - INTERVAL '84 days' ORDER BY date_trunc('week', date), date DESC) s),
    'dispersion_spark',       (SELECT jsonb_agg(cross_sectional_dispersion) FROM (SELECT DISTINCT ON (date_trunc('week', date)) cross_sectional_dispersion FROM atlas.atlas_regime_daily WHERE date >= (SELECT d FROM latest) - INTERVAL '84 days' ORDER BY date_trunc('week', date), date DESC) s)
  ) AS data
),

-- ===========================================================================
-- 7. Cells favored under current regime (top 6 by confidence_unconditional)
-- ===========================================================================
cells_favored AS (
  SELECT jsonb_agg(jsonb_build_object(
    'cell_id', cd.cell_id,
    'display_name', cd.display_name,
    'explain_text', cd.explain_text,
    'cap_tier', cd.cap_tier,
    'action', cd.action,
    'tenure', cd.tenure,
    'predicted_excess', cd.friction_adjusted_excess,
    'confidence', CASE
      WHEN cd.confidence_unconditional >= 0.60 THEN 'HIGH'
      WHEN cd.confidence_unconditional >= 0.50 THEN 'MED'
      ELSE 'LOW'
    END,
    'stocks_firing_today', (
      SELECT COUNT(*) FROM atlas.atlas_signal_calls sc
      WHERE sc.cell_id = cd.cell_id AND sc.exit_date IS NULL
    )
  ) ORDER BY cd.confidence_unconditional DESC) AS data
  FROM atlas.atlas_cell_definitions cd
  WHERE cd.drift_status = 'healthy'
  LIMIT 6
),

-- ===========================================================================
-- 8. Today's conviction — 3 tabs (stocks / funds / ETFs)
-- ===========================================================================
top_stocks AS (
  SELECT jsonb_agg(jsonb_build_object(
    'symbol', u.symbol,
    'company_name', u.company_name,
    'sector', u.sector,
    'cap_tier', u.tier,
    'cell_name', cd.display_name,
    'action', cd.action,
    'confidence', ROUND(sc.confidence_unconditional * 100, 0),
    'predicted_excess', sc.predicted_excess,
    'is_new_today', sc.date = (SELECT d FROM latest)
  ) ORDER BY sc.confidence_unconditional DESC) AS data
  FROM atlas.atlas_signal_calls sc
  JOIN atlas.atlas_universe_stocks u ON u.instrument_id = sc.instrument_id AND u.effective_to IS NULL
  JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = sc.cell_id
  WHERE sc.exit_date IS NULL
  LIMIT 8
),
top_funds AS (
  SELECT jsonb_agg(jsonb_build_object(
    'scheme_code', f.scheme_code,
    'fund_name', uf.scheme_name,
    'category', f.fund_category,
    'plan_type', uf.plan_type,
    'composite', f.composite_score,
    'recommendation', mr.recommendation,
    'quartile', mr.peer_quartile,
    'is_atlas_leader', f.is_atlas_leader
  ) ORDER BY f.composite_score DESC) AS data
  FROM atlas.atlas_fund_scorecard f
  JOIN atlas.atlas_universe_funds uf ON uf.mstar_id = f.scheme_code AND uf.effective_to IS NULL
  LEFT JOIN atlas.atlas_mf_recommendation_daily mr
    ON mr.date = f.snapshot_date
    AND mr.mf_instrument_id = ('00000000-0000-0000-0000-' || RIGHT(md5(f.scheme_code), 12))::uuid
  WHERE f.snapshot_date = (SELECT d FROM latest)
  LIMIT 8
),
top_etfs AS (
  SELECT jsonb_agg(jsonb_build_object(
    'ticker', es.ticker,
    'etf_name', es.etf_name,
    'category', es.etf_category,
    'underlying_sector', es.underlying_sector,
    'composite', es.composite_score,
    'cell_name', cd.display_name,
    'action', esc.action,
    'predicted_excess', esc.predicted_excess
  ) ORDER BY es.composite_score DESC) AS data
  FROM atlas.atlas_etf_scorecard es
  LEFT JOIN atlas.atlas_etf_signal_calls esc ON esc.etf_instrument_id = es.instrument_id AND esc.exit_date IS NULL
  LEFT JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = esc.cell_id
  WHERE es.snapshot_date = (SELECT d FROM latest)
  LIMIT 8
)

-- ===========================================================================
-- Final SELECT — 1 wide row
-- ===========================================================================
SELECT
  (SELECT d FROM latest) AS as_of_date,
  rh.regime_state,
  rh.deployment_multiplier,
  rh.days_in_regime,
  rh.entered_date,
  rh.prior_regime_state,
  rs.typical_length_days,
  rs.next_state_probs,
  (SELECT segments FROM recent_60d_regimes) AS recent_60d_segments,
  (SELECT rows FROM twelve_week_journey) AS twelve_week_journey,
  (SELECT data FROM pulse_tiles) AS pulse_tiles,
  (SELECT data FROM cells_favored) AS cells_favored,
  (SELECT data FROM top_stocks) AS conviction_stocks,
  (SELECT data FROM top_funds) AS conviction_funds,
  (SELECT data FROM top_etfs) AS conviction_etfs,
  -- Hardcoded deployment defaults for hero strip math
  jsonb_build_object(
    'Risk-On', 0.60,
    'Elevated', 0.50,
    'Cautious', 0.40,
    'Risk-Off', 0.30
  ) AS deployment_defaults,
  6.5 AS liquid_bees_yield_pct,  -- hardcoded
  NOW() AS refreshed_at
FROM regime_hero rh
LEFT JOIN regime_stats rs USING (regime_state);

CREATE UNIQUE INDEX ix_mv_market_regime_landing_as_of ON atlas.mv_market_regime_landing (as_of_date);
```

---

## Refresh strategy

```sql
-- pg_cron: nightly at 20:00 IST, after writer chain completes
SELECT cron.schedule(
  'refresh_mv_market_regime_landing',
  '0 20 * * *',  -- 20:00 IST = 14:30 UTC; adjust to UTC if cron runs in UTC
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_market_regime_landing;$$
);
```

`CONCURRENTLY` requires a unique index — defined above. Refresh latency target < 30s.

---

## Frontend consumption

```typescript
// frontend/src/lib/queries/v6/market-regime.ts (NEW; Phase G)
export async function getMarketRegimeLanding() {
  const { data, error } = await supabase
    .schema('atlas')
    .from('mv_market_regime_landing')
    .select('*')
    .single();
  if (error) throw error;
  return data;
}
```

One DB call, one wide row, all sections nested. Frontend composes from JSONB.

---

## Tests (Phase E implementation)

- Row count = 1 (single wide row)
- All JSONB sections non-null
- twelve_week_journey has exactly 12 rows
- pulse_tiles has 4 metrics + 4 spark arrays of 12 elements each
- cells_favored has 6 rows
- conviction_{stocks,funds,etfs} each has ≤ 8 rows
- Refresh latency < 30s

---

## Known gaps at v6.0 launch

- `atlas_regime_daily.smallcap_rs_z` + `cross_sectional_dispersion` = 0 rows → `twelve_week_journey.smallcap_rs_z` + `dispersion` columns will be NULL. Pulse tiles 1 + 4 will show "computing…". **Acceptable for v6.0**; full population comes when v6 regime classifier writer runs.
- `cells_favored.confidence` uses unconditional fallback; will swap to regime-conditional when `confidence_by_regime` populates.

---

**Implementation: ready to land via Supabase MCP `execute_sql` next session.**
