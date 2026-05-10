import type { CommentaryResult } from './stocks'

export type ETFPageAggregates = {
  total: number
  investable_count: number
  leader_count: number
  strong_count: number
  pct_leader_strong: number
  broad_investable_count: number
  sectoral_investable_count: number
  median_rs_pctile: number
  accel_count: number
  regime_state: string
  deployment_multiplier: number
}

type Condition = {
  test: (a: ETFPageAggregates) => boolean
  generate: (a: ETFPageAggregates) => string
}

const CONDITIONS: Condition[] = [
  {
    test: a => a.regime_state === 'Risk-Off',
    generate: a =>
      `Market is Risk-Off — ETF deployment at 0%. Broad market ETFs confirm systemic weakness. ${a.investable_count} ETFs remain RS-investable and can be added when regime conditions improve.`,
  },
  {
    test: a => a.pct_leader_strong < 0.10,
    generate: a =>
      `ETF leadership is thin: only ${(a.pct_leader_strong * 100).toFixed(0)}% (${a.leader_count + a.strong_count} of ${a.total}) are Leader or Strong under ${a.regime_state}. Narrow ETF breadth suggests sector rotation is concentrated — avoid broad exposure, prefer high-conviction sectoral names.`,
  },
  {
    test: a => a.broad_investable_count > a.sectoral_investable_count,
    generate: a =>
      `Defensive tilt: ${a.broad_investable_count} broad market ETFs are investable vs ${a.sectoral_investable_count} sectoral. Capital is rotating toward broad, defensive names — this favours large-cap exposure over sector bets under ${a.regime_state}.`,
  },
  {
    test: a => a.pct_leader_strong >= 0.30,
    generate: a =>
      `Broad ETF strength: ${(a.pct_leader_strong * 100).toFixed(0)}% of the ETF universe is Leader or Strong. Wide breadth under ${a.regime_state} (${Math.round(a.deployment_multiplier * 100)}% deployment) supports portfolio construction across sectors.`,
  },
  {
    test: () => true,
    generate: a =>
      `${a.leader_count + a.strong_count} ETFs are Leader or Strong (${(a.pct_leader_strong * 100).toFixed(0)}%), median RS at ${(a.median_rs_pctile * 100).toFixed(0)}th percentile. Under ${a.regime_state} at ${Math.round(a.deployment_multiplier * 100)}% deployment, ${a.investable_count} ETFs qualify for new positions.`,
  },
]

export function buildETFCommentary(aggregates: ETFPageAggregates): CommentaryResult {
  const condition = CONDITIONS.find(c => c.test(aggregates))!
  const narrative = condition.generate(aggregates)

  const contextCards = [
    { label: 'Investable', value: `${aggregates.investable_count} ETFs` },
    { label: 'Leader/Strong', value: `${aggregates.leader_count + aggregates.strong_count}` },
    { label: 'Broad Inv', value: `${aggregates.broad_investable_count}` },
    { label: 'Deployment', value: `${Math.round(aggregates.deployment_multiplier * 100)}%`, deltaPositive: aggregates.deployment_multiplier >= 0.7 },
  ]

  return { narrative, contextCards }
}
