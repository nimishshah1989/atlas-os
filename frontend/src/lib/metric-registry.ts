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
}

export function metric(key: string): MetricDef | null {
  return METRIC_REGISTRY[key] ?? null
}
