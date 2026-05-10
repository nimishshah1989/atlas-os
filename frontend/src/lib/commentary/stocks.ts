export type StocksPageAggregates = {
  total: number
  investable_count: number
  leader_count: number
  strong_count: number
  pct_leader_strong: number      // fraction 0–1
  median_rs_pctile: number       // fraction 0–1
  accel_count: number
  regime_state: string
  deployment_multiplier: number  // 0–1
}

export type CommentaryResult = {
  narrative: string
  contextCards: { label: string; value: string; delta?: string; deltaPositive?: boolean }[]
}

type Condition = {
  test: (a: StocksPageAggregates) => boolean
  generate: (a: StocksPageAggregates) => string
}

const CONDITIONS: Condition[] = [
  {
    test: a => a.regime_state === 'Risk-Off',
    generate: a =>
      `Market is Risk-Off — deployment at 0%. No new positions regardless of stock signals. ${a.investable_count} stocks remain investable by RS criteria and can be added when the regime improves.`,
  },
  {
    test: a => a.pct_leader_strong < 0.10,
    generate: a =>
      `Leadership is thin: only ${(a.pct_leader_strong * 100).toFixed(0)}% of stocks (${a.leader_count + a.strong_count}) are Leader or Strong under ${a.regime_state} (${Math.round(a.deployment_multiplier * 100)}% deployment). Narrow markets often precede corrections — prefer high-conviction names from the investable list.`,
  },
  {
    test: a => a.pct_leader_strong >= 0.30,
    generate: a =>
      `Broad strength: ${(a.pct_leader_strong * 100).toFixed(0)}% of the universe is Leader or Strong — a wide breadth reading. Under ${a.regime_state} at ${Math.round(a.deployment_multiplier * 100)}% deployment, ${a.investable_count} stocks qualify for new positions.`,
  },
  {
    test: () => true,
    generate: a =>
      `${a.leader_count + a.strong_count} stocks are Leader or Strong (${(a.pct_leader_strong * 100).toFixed(0)}%) with a median RS percentile of ${(a.median_rs_pctile * 100).toFixed(0)}th. Under ${a.regime_state} (${Math.round(a.deployment_multiplier * 100)}% deployment), ${a.investable_count} meet all entry criteria.`,
  },
]

export function buildStocksCommentary(aggregates: StocksPageAggregates): CommentaryResult {
  const condition = CONDITIONS.find(c => c.test(aggregates))!
  const narrative = condition.generate(aggregates)

  const contextCards = [
    {
      label: 'Investable',
      value: `${aggregates.investable_count} stocks`,
    },
    {
      label: 'Leader/Strong',
      value: `${aggregates.leader_count + aggregates.strong_count}`,
    },
    {
      label: 'Deployment',
      value: `${Math.round(aggregates.deployment_multiplier * 100)}%`,
      deltaPositive: aggregates.deployment_multiplier >= 0.7,
    },
    {
      label: 'Accelerating',
      value: `${aggregates.accel_count}`,
    },
  ]

  return { narrative, contextCards }
}
