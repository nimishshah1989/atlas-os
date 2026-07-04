// Plain-English description of what a portfolio's strategy actually does — turns
// the stored params into sentences a person can read, so a system-generated
// policy is never a black box. Pure + client-safe.

export type StrategyExplainer = {
  headline: string
  entry: string
  exit: string
  universe: string
  selection: string
  sizing: string
  guards: string[] // extra conditions layered on the base trend rule
}

const ordinal = (n: number) => `${n}-day`
const universeText = (assetClasses: string[]): string => {
  const names = assetClasses.map((a) => (a === 'stock' ? 'stocks' : a === 'etf' ? 'ETFs' : 'mutual funds'))
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
  const scored = assetClasses.includes('stock') ? ' drawn from the Atlas-scored Nifty 500' : ''
  return `Trades ${list}${scored}.`
}

export function describeStrategy(
  kind: 'strategy' | 'basket',
  params: Record<string, unknown> | null,
  assetClasses: string[],
  maxPositionPct: number,
  strategyKey: string | null,
): StrategyExplainer | null {
  const slots = Math.floor(1 / maxPositionPct)
  const capPct = Math.round(maxPositionPct * 100)

  if (kind === 'basket') {
    return {
      headline: 'A hand-picked basket — no automated rule',
      entry: 'Instruments are added by the fund manager; each is bought at the last EOD close when added.',
      exit: 'Positions are held until the fund manager sells them.',
      universe: universeText(assetClasses),
      selection: 'The fund manager chooses every holding directly.',
      sizing: `Each position is sized up to ${capPct}% of the portfolio (about ${slots} equal slots), execution costs included.`,
      guards: [],
    }
  }

  if (!params || (strategyKey !== 'ema_cross' && strategyKey !== 'atlas_policy')) return null

  const fast = Number(params.fast)
  const slow = Number(params.slow)
  const guards: string[] = []

  if (strategyKey === 'atlas_policy') {
    if (params.confirm_200)
      guards.push('the price must also be above its 200-day EMA — so it only buys names in a confirmed long-term uptrend, not short-lived bounces')
    if (params.rs_min != null)
      guards.push(`the name must be outperforming the NIFTY 500 over the last 3 months by at least ${(Number(params.rs_min) * 100).toFixed(0)}% — it only chases relative strength`)
    if (params.min_composite != null)
      guards.push(`the name's Atlas composite score must be at least ${params.min_composite} — it filters out low-conviction names`)
    if (params.regime_gate)
      guards.push('when the overall market regime turns Risk-Off (or a dislocation is flagged), it exits everything and moves fully to cash — a market-wide circuit breaker')
  }

  const guardClause = guards.length
    ? ` To enter, all of the following must ALSO hold at the same time: ${guards.map((g) => g.split(' — ')[0]).join('; ')}.`
    : ''

  return {
    headline:
      strategyKey === 'ema_cross'
        ? `A ${fast}/${slow} EMA crossover rule`
        : `An Atlas policy built on a ${fast}/${slow} EMA crossover`,
    entry: `Buys a name on the day its ${ordinal(fast)} exponential moving average (a fast measure of price trend) crosses ABOVE its ${ordinal(slow)} average — the moment an uptrend begins.${guardClause}`,
    exit:
      strategyKey === 'atlas_policy' && params.regime_gate
        ? `Sells on the day the ${ordinal(fast)} average crosses back BELOW the ${ordinal(slow)} — or immediately if any entry condition breaks (including the market turning Risk-Off).`
        : `Sells on the day the ${ordinal(fast)} average crosses back BELOW the ${ordinal(slow)} average — the moment the uptrend reverses.`,
    universe: universeText(assetClasses),
    selection: assetClasses.includes('stock')
      ? `When more names qualify than there are open slots, it holds the ones with the highest Atlas composite score on the signal day.`
      : `When more names qualify than there are open slots, it holds them in signal order.`,
    sizing: `Starts 100% in cash and only ever buys on a fresh signal. Each position is capped at ${capPct}% of portfolio value — about ${slots} equal slots — with execution costs deducted and trades filled at the next session's close (no look-ahead).`,
    guards,
  }
}
