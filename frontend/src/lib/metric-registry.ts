// frontend/src/lib/metric-registry.ts
export interface MetricDef { label: string; definition: string; formula: string }

export const METRIC_REGISTRY: Record<string, MetricDef> = {
  scorecard_trend_pct: {
    label: 'Stage 2 Universe %',
    definition: 'Percentage of the Nifty 500 universe currently classified as Stage 2a, 2b, or 2c — the investable uptrend stages in Weinstein methodology. Higher = more stocks are in actionable uptrends.',
    formula: 'COUNT(state IN stage_2a/2b/2c) / COUNT(*) on latest date · source: atlas_stock_state_daily classifier_version=v2.0-validated.',
  },
  scorecard_breadth_pct: {
    label: 'EMA-50 Participation',
    definition: 'Fraction of the Nifty 500 trading above their 50-day EMA on the latest date. The primary breadth measure. Above 50% = majority in medium-term uptrend; below 40% = narrow/unhealthy market.',
    formula: 'pct_above_ema_50 · source: atlas_market_regime_daily (most recent row).',
  },
  scorecard_momentum_net: {
    label: 'Stage 2 Net Inflow (5D)',
    definition: 'Net count of stocks entering Stage 2 (2a/2b/2c) minus stocks leaving Stage 2 over the last 5 trading days. Positive = more breakouts than breakdowns. A leading indicator of breadth improvement.',
    formula: 'stage_2_count(today) − stage_2_count(5 trading days ago) · source: atlas_stock_state_daily.',
  },
  scorecard_participation: {
    label: 'Leadership Breadth',
    definition: 'Average cross-sector leadership breadth: 1 minus leadership_concentration, averaged across all sectors on the latest date. Higher = leadership is distributed across many stocks (healthy). Lower = a few names driving sector returns (fragile).',
    formula: 'AVG(1 - leadership_concentration) across sectors · source: atlas_sector_metrics_daily (latest date).',
  },
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
  india_vix: {
    label: 'India VIX',
    definition: 'India VIX is the NSE\'s implied volatility index derived from Nifty 50 options. Values above 20 indicate elevated fear in the options market. Used as a regime corroborator — high VIX suppresses deployment even when breadth is otherwise constructive.',
    formula: 'NSE-published daily fixing. Stored in atlas_market_regime_daily.india_vix. Thresholds: <18 = calm, 18–25 = elevated, >25 = stressed.',
  },
  ad_ratio: {
    label: 'Advance/Decline Ratio',
    definition: 'Ratio of stocks advancing to stocks declining across the 750-stock Nifty 500 universe on a given day. Values above 1 mean more stocks are rising than falling — a basic breadth health check.',
    formula: 'advances_count / declines_count · source: atlas_market_regime_daily. Computed from NSE daily price changes.',
  },
  ad_line_slope_21: {
    label: 'A/D Line Slope (21D)',
    definition: '21-day slope of the cumulative Advance/Decline line, expressed in standard-deviation units of daily A/D net changes over the same window. Positive = A/D line is rising (healthy internals). Divergence between this and the index is an early warning.',
    formula: 'OLS slope of ad_line over last 21 trading days, divided by stddev(daily_net_advances, 21D) · source: atlas_market_regime_daily.',
  },
  mcclellan_oscillator: {
    label: 'McClellan Oscillator',
    definition: 'Short-term breadth momentum oscillator. The difference between the 19-day EMA and 39-day EMA of daily net advances (advances minus declines). Positive = breadth is accelerating upward; negative = decelerating. Zero-line crossovers are transition signals.',
    formula: 'EMA(19, net_advances) − EMA(39, net_advances) · source: atlas_market_regime_daily.mcclellan_oscillator.',
  },
  mcclellan_summation: {
    label: 'McClellan Summation Index',
    definition: 'Cumulative running sum of the McClellan Oscillator. An intermediate-term breadth trend indicator. Structurally bullish above zero; deep negative readings require sustained improvement to reverse. Slower and more reliable than the oscillator for regime change.',
    formula: 'CUMSUM(mcclellan_oscillator) reset at market structure change · source: atlas_market_regime_daily.mcclellan_summation.',
  },
  net_new_highs: {
    label: 'Net New Highs (52W)',
    definition: 'New 52-week highs minus new 52-week lows. Positive = more stocks at annual highs than lows (healthy internal expansion). Sustained negative readings — persistent for 30+ days — have historically defined bear markets.',
    formula: 'new_52w_highs − new_52w_lows · source: atlas_market_regime_daily. Rolling 252-trading-day lookback for high/low classification.',
  },
  new_high_low_ratio: {
    label: 'New High/Low Ratio',
    definition: 'Normalizes new 52-week highs vs new lows. Values above 1 are bullish (more highs than lows). Smooths the absolute count to adjust for universe size and avoids zero-denominator on days with no new lows.',
    formula: 'new_52w_highs / MAX(new_52w_lows, 1) · source: atlas_market_regime_daily.',
  },
}

export function metric(key: string): MetricDef | null {
  return METRIC_REGISTRY[key] ?? null
}
