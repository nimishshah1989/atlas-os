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

function describeRankPolicy(
  p: Record<string, unknown>,
  assetClasses: string[],
  maxPositionPct: number,
): StrategyExplainer {
  const slots = Math.floor(1 / maxPositionPct)
  const capPct = Math.round(maxPositionPct * 100)
  const buf = Number(p.exit_buffer ?? 5)
  const mode = String(p.mode)
  const M: Record<string, { headline: string; entry: string; exitCore: string }> = {
    sector_leaders: {
      headline: `Sector Leaders — the top ${p.n_per_sector} names in each of the ${p.n_sectors} strongest sectors`,
      entry: `Every session, sectors are ranked by the average Atlas conviction of their constituents. A name enters when its sector is among the top ${p.n_sectors} AND it is one of the top ${p.n_per_sector} names in that sector by composite score.`,
      exitCore: `its sector falls out of the top ${Number(p.n_sectors) + buf}, or the name drops below the top ${Number(p.n_per_sector) + buf} in its sector`,
    },
    conviction: {
      headline: `Conviction Concentrate — the ${p.n_names} highest-conviction names in the market`,
      entry: `Every session, all scored names are ranked by Atlas composite. A name enters when it is in the top ${p.n_names} market-wide (at most ${p.sector_cap} names from any one sector).`,
      exitCore: `it falls below rank ${Number(p.n_names) + buf}`,
    },
    quality_momentum: {
      headline: `Quality Momentum — top-conviction names that are ALSO outperforming and in an uptrend`,
      entry: `A name enters only when it is top-${p.n_names} by Atlas composite AND outperforming the NIFTY 500 over 3 months AND above its 200-day EMA — conviction, relative strength and trend all confirmed at once.`,
      exitCore: `it falls below rank ${Number(p.n_names) + buf}, starts underperforming the NIFTY 500, or loses its 200-day EMA`,
    },
    rotation: {
      headline: `Sector Rotation — catching sectors as they turn, before they lead`,
      entry: `Sectors are ranked by how much their strength rank has IMPROVED over the last ${p.lookback} sessions, starting from a below-median base. A name enters when its sector is among the ${p.n_sectors} fastest improvers and it is top-${p.n_per_sector} there by composite.`,
      exitCore: `its sector stops improving (and hasn't graduated to an outright leader), or the name drops past the buffer`,
    },
  }
  const m = M[mode] ?? M.conviction
  return {
    headline: m.headline,
    entry: m.entry,
    exit: `Holds until ${m.exitCore}. The buffer is deliberate hysteresis — winners are left to run instead of being churned out on small rank wiggles, which also lets gains reach the long-term tax rate.`,
    universe: `Trades stocks drawn from the Atlas-scored Nifty 500, evaluated every session.`,
    selection: `When more names qualify than there are open slots, the highest Atlas composite wins the slot.`,
    sizing: `Starts 100% in cash and buys the qualifying set at the next session's close (no look-ahead). Each position capped at ${capPct}% (~${slots} slots), execution costs in the NAV, FIFO tax ledger on every sale.`,
    guards: [],
  }
}

const CAP_LABEL: Record<string, string> = {
  'India Fund Large-Cap': 'large-cap',
  'India Fund Mid-Cap': 'mid-cap',
  'India Fund Small-Cap': 'small-cap',
}
const capName = (cats: unknown): string => {
  const arr = Array.isArray(cats) ? cats.map((c) => CAP_LABEL[String(c)] ?? String(c)) : []
  return arr.length ? arr.join(' & ') + ' equity mutual funds' : 'equity mutual funds'
}

function describeFundCrossover(
  p: Record<string, unknown>,
  maxPositionPct: number,
): StrategyExplainer {
  const fast = Number(p.fast)
  const slow = Number(p.slow)
  const slots = Math.floor(1 / maxPositionPct)
  const sleeves = p.sleeves as { weight: number; categories: string[] }[] | undefined
  const universe = sleeves
    ? `A fixed-allocation blend across three capital sleeves: ${sleeves
        .map((s) => `${Math.round(s.weight * 100)}% ${capName(s.categories)}`)
        .join(', ')} — each sleeve runs the same crossover on its own budget and manages its own cash.`
    : `Trades ${capName(p.fund_categories)}${p.fund_categories ? '' : ' — the whole equity-fund set, no cap restriction'}, using each fund's NAV.`
  return {
    headline: `A ${fast}/${slow} EMA crossover on mutual-fund NAVs — a long-horizon golden-cross rule`,
    entry: `Buys a fund on the day its ${ordinal(fast)} NAV moving average crosses ABOVE its ${ordinal(slow)} — a golden cross, the classic long-term uptrend signal (the slow ${slow}-day average suits the smoother, slower-moving nature of fund NAVs).`,
    exit: `Sells on the day the ${ordinal(fast)} average crosses back BELOW the ${ordinal(slow)} — the death cross.`,
    universe,
    selection: 'When more funds qualify than there are slots, they fill in signal order (deterministic).',
    sizing: `Starts fully in cash, buys only on a fresh golden cross, ${Math.round(maxPositionPct * 100)}% per fund (~${slots} slots). NAV is net of the MF exit load (charged when a fund is redeemed within a year), and post-tax returns apply equity-MF capital-gains rules (20% short-term, 12.5% long-term after a year).`,
    guards: [],
  }
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

  if (kind === 'basket' && params?.desk === true) {
    const slots = Math.floor(1 / maxPositionPct)
    return {
      headline: 'An agent-run trading desk over Atlas’s ranks (forward-only)',
      entry: 'Every night after the marks, a Scout agent reads the fresh Atlas data (composite ranks, sector strength, relative strength, regime) and proposes additions; a Risk & Tax officer approves, resizes, defers or vetoes each; the PM buys only Risk-approved names, recording a thesis and a falsifiable exit condition per position.',
      exit: 'The Scout checks every holding’s stated exit condition and rank health daily; sells go through the same Risk review (a short-term-gain exit is deferred unless the thesis-break is urgent). The whole book exits new-entry mode in Risk-Off regimes.',
      universe: universeText(assetClasses),
      selection: 'Judgment over the ranked watchlist — the agents choose among Atlas’s top-conviction names, never outside them.',
      sizing: `One standard slot per buy (~${Math.round(maxPositionPct * 100)}% of the book, ${slots} slots), execution costs and FIFO tax included. Hard caps (orders/night, per-sector, Risk-Off block) are enforced in code, not by the model.`,
      guards: ['This desk is never backtested — LLM hindsight makes historical replays meaningless; it is judged live against its deterministic twin and NIFTY 500.'],
    }
  }
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

  if (params && strategyKey === 'rank_policy') return describeRankPolicy(params, assetClasses, maxPositionPct)
  if (params && strategyKey === 'ema_cross' && assetClasses.includes('fund'))
    return describeFundCrossover(params, maxPositionPct)
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
