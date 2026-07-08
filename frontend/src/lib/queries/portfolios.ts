// Portfolio board data — atlas_foundation.portfolio_* ONLY. Holdings are DERIVED
// from the immutable trade log (no positions table); NAV/backtest series come from
// portfolio_nav_daily written by scripts/foundation/portfolio_run.py. RULE #0: every
// number is a stored engine output or a stored market price — nothing derived here
// beyond joins and percentages.
import 'server-only'
import sql from '@/lib/db'
import { computeWindowMetrics, type WindowMetrics } from '@/lib/portfolioMetrics'
import { describeStrategy } from '@/lib/strategyDescription'

export type PortfolioCategory = 'rule' | 'system' | 'basket'

export type PortfolioSummary = {
  id: string
  name: string
  kind: 'strategy' | 'basket'
  category: PortfolioCategory
  strategyLabel: string | null
  assetClasses: string[]
  initialCapital: number
  maxPositionPct: number
  inceptionDate: string
  navDate: string | null
  nav: number | null
  cash: number | null
  nPositions: number | null
  sinceInceptionPct: number | null
  btTotalPct: number | null
  btYears: number | null
  btCagr5Pct: number | null
  params: Record<string, unknown> | null
  strategyKey: string | null
}

const DESK_CHARTER_LABEL: Record<string, string> = {
  sector_leaders: 'Sector Leaders',
  conviction: 'Conviction',
  quality_momentum: 'Quality Momentum',
  rotation: 'Rotation',
}

const strategyLabel = (key: string | null, params: Record<string, unknown> | null): string | null => {
  if (!params) return key
  if (params.desk === true)
    return `Agent desk · ${DESK_CHARTER_LABEL[String(params.charter)] ?? String(params.charter)}`
  if (key === 'ema_cross') return `EMA ${params.fast}/${params.slow} crossover`
  if (key === 'rank_policy') {
    const names: Record<string, string> = {
      sector_leaders: 'Sector Leaders (rank-driven)',
      conviction: 'Conviction Concentrate (rank-driven)',
      quality_momentum: 'Quality Momentum (rank-driven)',
      rotation: 'Sector Rotation (rank-driven)',
    }
    return names[String(params.mode)] ?? 'Rank-driven'
  }
  if (key === 'atlas_policy') {
    const parts = [`EMA ${params.fast}/${params.slow}`]
    if (params.confirm_200) parts.push('>200')
    if (params.rs_min != null) parts.push(`RS≥${(Number(params.rs_min) * 100).toFixed(0)}%`)
    if (params.min_composite != null) parts.push(`comp≥${params.min_composite}`)
    if (params.regime_gate) parts.push('regime-gated')
    return parts.join(' · ')
  }
  return key
}

export async function getPortfolios(): Promise<PortfolioSummary[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT m.portfolio_id, m.name, m.kind, m.origin, m.strategy_key, m.params, m.asset_classes,
           m.initial_capital, m.max_position_pct, m.inception_date::text AS inception_date,
           ln.date::text AS nav_date, ln.nav, ln.cash, ln.n_positions,
           bt.total_pct AS bt_total_pct, bt.years AS bt_years, bt.cagr5_pct AS bt_cagr5_pct
    FROM atlas_foundation.portfolio_master m
    LEFT JOIN LATERAL (
      SELECT date, nav, cash, n_positions FROM atlas_foundation.portfolio_nav_daily n
      WHERE n.portfolio_id = m.portfolio_id AND n.run_type = 'live'
      ORDER BY date DESC LIMIT 1
    ) ln ON true
    LEFT JOIN LATERAL (
      SELECT (l.nav / nullif(f.nav, 0) - 1) * 100 AS total_pct,
             (l.date - f.date) / 365.25 AS years,
             -- uniform card metric: annualized return over the LAST 5 backtest
             -- years (or the full span when shorter, still annualized; >=1y only)
             CASE WHEN l.date - b.date >= 365 THEN
               (power((l.nav / nullif(b.nav, 0))::float8,
                      1.0 / ((l.date - b.date) / 365.25)) - 1) * 100
             END AS cagr5_pct
      FROM (SELECT nav, date FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type = 'backtest'
            ORDER BY date ASC LIMIT 1) f,
           (SELECT nav, date FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type = 'backtest'
            ORDER BY date DESC LIMIT 1) l,
           LATERAL (SELECT nav, date FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type = 'backtest'
              AND date >= l.date - interval '5 years'
            ORDER BY date ASC LIMIT 1) b
    ) bt ON true
    WHERE m.status = 'active'
    ORDER BY m.created_at
  `
  return rows.map((r) => ({
    id: String(r.portfolio_id),
    name: String(r.name),
    kind: r.kind as 'strategy' | 'basket',
    category: (r.origin === 'system' ? 'system' : r.kind === 'basket' ? 'basket' : 'rule') as PortfolioCategory,
    strategyLabel: strategyLabel(r.strategy_key as string | null, r.params as Record<string, unknown> | null),
    assetClasses: (r.asset_classes as string[]) ?? [],
    initialCapital: Number(r.initial_capital),
    maxPositionPct: Number(r.max_position_pct),
    inceptionDate: String(r.inception_date),
    navDate: r.nav_date ? String(r.nav_date) : null,
    nav: r.nav != null ? Number(r.nav) : null,
    cash: r.cash != null ? Number(r.cash) : null,
    nPositions: r.n_positions != null ? Number(r.n_positions) : null,
    sinceInceptionPct:
      r.nav != null ? (Number(r.nav) / Number(r.initial_capital) - 1) * 100 : null,
    btTotalPct: r.bt_total_pct != null ? Number(r.bt_total_pct) : null,
    btYears: r.bt_years != null ? Number(r.bt_years) : null,
    btCagr5Pct: r.bt_cagr5_pct != null ? Number(r.bt_cagr5_pct) : null,
    params: (r.params as Record<string, unknown> | null) ?? null,
    strategyKey: r.strategy_key ? String(r.strategy_key) : null,
  }))
}

export type Holding = {
  assetClass: string
  instrumentKey: string
  symbol: string
  name: string | null
  sector: string | null
  qty: number
  netCost: number
  lastPrice: number | null
  value: number | null
  // Atlas read (stocks/ETFs from the latest lens snapshot; funds null)
  composite: number | null
  lensTech: number | null
  lensFlow: number | null
  lensVal: number | null
  rs3m: number | null
  aboveEma50: boolean | null
  aboveEma200: boolean | null
  riskFlags: string | null
}

export type AtlasRead = {
  weightedComposite: number | null
  breadth50: number | null // % of equity holdings (by value) above their 50 EMA
  breadth200: number | null
  weightedRs3m: number | null
  flaggedCount: number
  sectorVsBenchmark: { sector: string; port: number; bench: number }[]
}

export type NavPointRow = { d: string; nav: number }
export type TradeRow = {
  date: string
  symbol: string
  side: string
  qty: number
  price: number
  value: number
  cost: number | null
  realizedPnl: number | null
  holdingDays: number | null
  taxBucket: string | null
  tax: number | null
  reason: string
  runType: string
}

export type CostTaxTotals = {
  costs: number
  realized: number
  tax: number
  nTrades: number
}

export type PortfolioDetail = {
  summary: PortfolioSummary
  holdings: Holding[]
  liveNav: NavPointRow[]
  backtestNav: NavPointRow[]
  backtestRawNav: NavPointRow[] // risk-managed-OFF comparison (rank/desk books only)
  benchmark: NavPointRow[] // NIFTY 500 close over the backtest window
  trades: TradeRow[]
  totals: { live: CostTaxTotals; backtest: CostTaxTotals }
  atlas: AtlasRead
  policyJournal: PolicyJournalEntry[]
  deskJournal: DeskCycle[]
  deskLessons: { lesson: string; confidence: number }[]
}

export type DeskCycle = {
  d: string
  scout: Record<string, unknown> | null
  risk: Record<string, unknown> | null
  pm: Record<string, unknown> | null
  applied: Record<string, unknown>[]
  errors: string[]
}

export type PolicyJournalEntry = {
  ts: string
  kind: 'evaluation' | 'change'
  oldParams: Record<string, unknown> | null
  newParams: Record<string, unknown> | null
  evidence: Record<string, unknown>
}

export async function getPortfolioDetail(id: string): Promise<PortfolioDetail | null> {
  const all = await getPortfolios()
  const summary = all.find((p) => p.id === id)
  if (!summary) return null

  // positions first, then last prices via three small PK-indexed lookups (a single
  // correlated union here blew the pooler's statement timeout on full-history scans)
  const pos = await sql<Array<Record<string, unknown>>>`
    SELECT asset_class, instrument_key, symbol,
           sum(CASE WHEN side = 'buy' THEN qty ELSE -qty END) AS qty,
           sum(CASE WHEN side = 'buy' THEN value ELSE -value END) AS net_cost
    FROM atlas_foundation.portfolio_trades
    WHERE portfolio_id = ${id} AND run_type = 'live'
    GROUP BY 1, 2, 3
    HAVING sum(CASE WHEN side = 'buy' THEN qty ELSE -qty END) <> 0
  `
  const keysOf = (cls: string) =>
    pos.filter((p) => p.asset_class === cls).map((p) => String(p.instrument_key))
  const [stockKeys, etfKeys, fundKeys] = [keysOf('stock'), keysOf('etf'), keysOf('fund')]
  const meta = new Map<string, { sector: string | null; name: string | null }>()
  const equityKeys = [...stockKeys, ...etfKeys]
  if (equityKeys.length) {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT instrument_id::text AS k, sector, name FROM atlas_foundation.instrument_master
      WHERE instrument_id = ANY (${equityKeys}::uuid[])
    `
    for (const r of rows)
      meta.set(String(r.k), { sector: r.sector ? String(r.sector) : null, name: r.name ? String(r.name) : null })
  }
  const lastPrice = new Map<string, number>()
  if (stockKeys.length) {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT DISTINCT ON (instrument_id) instrument_id::text AS k, close_adj AS price
      FROM atlas_foundation.ohlcv_stock
      WHERE instrument_id = ANY (${stockKeys}::uuid[]) AND close_adj > 0
      ORDER BY instrument_id, date DESC
    `
    for (const r of rows) lastPrice.set(String(r.k), Number(r.price))
  }
  if (etfKeys.length) {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT DISTINCT ON (i.instrument_id) i.instrument_id::text AS k, e.close_adj AS price
      FROM atlas_foundation.instrument_master i
      JOIN atlas_foundation.ohlcv_etf e ON e.ticker = i.symbol
      WHERE i.instrument_id = ANY (${etfKeys}::uuid[]) AND e.close_adj > 0
      ORDER BY i.instrument_id, e.date DESC
    `
    for (const r of rows) lastPrice.set(String(r.k), Number(r.price))
  }
  if (fundKeys.length) {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT DISTINCT ON (mstar_id) mstar_id AS k, nav AS price
      FROM atlas_foundation.de_mf_nav_daily
      WHERE mstar_id = ANY (${fundKeys}) AND nav > 0
      ORDER BY mstar_id, nav_date DESC
    `
    for (const r of rows) lastPrice.set(String(r.k), Number(r.price))
  }
  // Atlas lens read for equity holdings (latest snapshot + latest technicals)
  const lens = new Map<string, Record<string, unknown>>()
  if (equityKeys.length) {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT s.instrument_id::text AS k, s.composite, s.technical, s.flow, s.valuation,
             s.risk_flags, t.above_ema_50, t.above_ema_200, t.rs_3m_n500
      FROM atlas_foundation.atlas_lens_scores_daily s
      LEFT JOIN atlas_foundation.technical_daily t
        ON t.instrument_id = s.instrument_id
       AND t.date = (SELECT max(date) FROM atlas_foundation.technical_daily)
      WHERE s.instrument_id = ANY (${equityKeys}::uuid[])
        AND s.date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily)
    `
    for (const r of rows) lens.set(String(r.k), r)
  }
  const num = (v: unknown) => (v == null ? null : Number(v))
  const holdings: Holding[] = pos
    .map((r) => {
      const k = String(r.instrument_key)
      const price = lastPrice.get(k) ?? null
      const qty = Number(r.qty)
      const m = meta.get(k)
      const l = lens.get(k)
      return {
        assetClass: String(r.asset_class),
        instrumentKey: k,
        symbol: String(r.symbol),
        name: m?.name ?? null,
        sector: m?.sector ?? null,
        qty,
        netCost: Number(r.net_cost),
        lastPrice: price,
        value: price != null ? qty * price : null,
        composite: num(l?.composite),
        lensTech: num(l?.technical),
        lensFlow: num(l?.flow),
        lensVal: num(l?.valuation),
        rs3m: num(l?.rs_3m_n500),
        aboveEma50: l?.above_ema_50 == null ? null : Boolean(l.above_ema_50),
        aboveEma200: l?.above_ema_200 == null ? null : Boolean(l.above_ema_200),
        riskFlags: l?.risk_flags ? String(l.risk_flags) : null,
      }
    })
    .sort((a, b) => (b.value ?? -1) - (a.value ?? -1))
  const nav = (runType: string) => sql<Array<Record<string, unknown>>>`
    SELECT date::text AS d, nav FROM atlas_foundation.portfolio_nav_daily
    WHERE portfolio_id = ${id} AND run_type = ${runType} ORDER BY date
  `
  const [liveNav, backtestNav, backtestRawNav] = await Promise.all([
    nav('live'),
    nav('backtest'),
    nav('backtest_raw'),
  ])
  const btStart = backtestNav[0]?.d ?? summary.inceptionDate
  const benchmark = await sql<Array<Record<string, unknown>>>`
    SELECT date::text AS d, close AS nav FROM atlas_foundation.index_prices
    WHERE index_code = 'NIFTY 500' AND date >= ${String(btStart)} ORDER BY date
  `
  const trades = await sql<Array<Record<string, unknown>>>`
    SELECT trade_date::text AS date, symbol, side, qty, price, value, cost,
           realized_pnl, holding_days, tax_bucket, tax, reason, run_type
    FROM atlas_foundation.portfolio_trades
    WHERE portfolio_id = ${id}
    ORDER BY trade_date DESC, trade_id DESC LIMIT 400
  `
  const totalRows = await sql<Array<Record<string, unknown>>>`
    SELECT run_type, count(*) AS n, coalesce(sum(cost), 0) AS costs,
           coalesce(sum(realized_pnl), 0) AS realized, coalesce(sum(tax), 0) AS tax
    FROM atlas_foundation.portfolio_trades
    WHERE portfolio_id = ${id} GROUP BY run_type
  `
  const totalsFor = (rt: string): CostTaxTotals => {
    const r = totalRows.find((x) => x.run_type === rt)
    return {
      costs: r ? Number(r.costs) : 0,
      realized: r ? Number(r.realized) : 0,
      tax: r ? Number(r.tax) : 0,
      nTrades: r ? Number(r.n) : 0,
    }
  }
  // portfolio-level Atlas read (value-weighted over holdings that carry the signal)
  const wavg = (get: (h: Holding) => number | null): number | null => {
    const rows = holdings.filter((h) => h.value != null && get(h) != null)
    const tot = rows.reduce((a, h) => a + (h.value as number), 0)
    return tot > 0 ? rows.reduce((a, h) => a + (h.value as number) * (get(h) as number), 0) / tot : null
  }
  const share = (pred: (h: Holding) => boolean | null): number | null => {
    const rows = holdings.filter((h) => h.value != null && pred(h) != null)
    const tot = rows.reduce((a, h) => a + (h.value as number), 0)
    return tot > 0
      ? (rows.filter((h) => pred(h)).reduce((a, h) => a + (h.value as number), 0) / tot) * 100
      : null
  }
  const benchRows = await sql<Array<Record<string, unknown>>>`
    SELECT im.sector, sum(dic.weight_pct) AS w
    FROM atlas_foundation.de_index_constituents dic
    JOIN atlas_foundation.instrument_master im USING (instrument_id)
    WHERE dic.index_code = 'NIFTY 500' AND dic.effective_to IS NULL AND im.sector IS NOT NULL
    GROUP BY 1
  `
  const bench = new Map(benchRows.map((r) => [String(r.sector), Number(r.w)]))
  const totVal = holdings.reduce((a, h) => a + (h.value ?? 0), 0)
  const portBySector = new Map<string, number>()
  for (const h of holdings) {
    if (h.value == null) continue
    const sec = h.sector ?? (h.assetClass === 'fund' ? 'Funds' : 'Unclassified')
    portBySector.set(sec, (portBySector.get(sec) ?? 0) + h.value)
  }
  const sectorVsBenchmark = [...new Set([...portBySector.keys()])]
    .map((sector) => ({
      sector,
      port: totVal > 0 ? ((portBySector.get(sector) ?? 0) / totVal) * 100 : 0,
      bench: bench.get(sector) ?? 0,
    }))
    .sort((a, b) => b.port - a.port)
  const flagged = (h: Holding) =>
    h.riskFlags != null && !['[]', '{}', ''].includes(h.riskFlags.trim())
  const atlas: AtlasRead = {
    weightedComposite: wavg((h) => h.composite),
    breadth50: share((h) => h.aboveEma50),
    breadth200: share((h) => h.aboveEma200),
    weightedRs3m: wavg((h) => h.rs3m),
    flaggedCount: holdings.filter(flagged).length,
    sectorVsBenchmark,
  }

  const journal = await sql<Array<Record<string, unknown>>>`
    SELECT ts::text AS ts, kind, old_params, new_params, evidence
    FROM atlas_foundation.portfolio_policy_journal
    WHERE portfolio_id = ${id} ORDER BY ts DESC LIMIT 20
  `
  const deskJournal = await sql<Array<Record<string, unknown>>>`
    SELECT cycle_date::text AS d, scout, risk, pm, applied, errors
    FROM atlas_foundation.desk_journal
    WHERE portfolio_id = ${id} ORDER BY cycle_date DESC, ts DESC LIMIT 15
  `
  const deskLessons = await sql<Array<Record<string, unknown>>>`
    SELECT lesson, confidence FROM atlas_foundation.desk_lessons
    WHERE portfolio_id = ${id} AND active ORDER BY confidence DESC, ts DESC LIMIT 6
  `

  const toNav = (rs: Array<Record<string, unknown>>): NavPointRow[] =>
    rs.map((r) => ({ d: String(r.d), nav: Number(r.nav) }))
  return {
    summary,
    holdings,
    liveNav: toNav(liveNav),
    backtestNav: toNav(backtestNav),
    backtestRawNav: toNav(backtestRawNav),
    benchmark: toNav(benchmark),
    trades: trades.map((r) => ({
      date: String(r.date),
      symbol: String(r.symbol),
      side: String(r.side),
      qty: Number(r.qty),
      price: Number(r.price),
      value: Number(r.value),
      cost: r.cost != null ? Number(r.cost) : null,
      realizedPnl: r.realized_pnl != null ? Number(r.realized_pnl) : null,
      holdingDays: r.holding_days != null ? Number(r.holding_days) : null,
      taxBucket: r.tax_bucket ? String(r.tax_bucket) : null,
      tax: r.tax != null ? Number(r.tax) : null,
      reason: String(r.reason),
      runType: String(r.run_type),
    })),
    totals: { live: totalsFor('live'), backtest: totalsFor('backtest') },
    atlas,
    policyJournal: journal.map((r) => ({
      ts: String(r.ts),
      kind: r.kind as 'evaluation' | 'change',
      oldParams: (r.old_params as Record<string, unknown> | null) ?? null,
      newParams: (r.new_params as Record<string, unknown> | null) ?? null,
      evidence: (r.evidence as Record<string, unknown>) ?? {},
    })),
    deskJournal: deskJournal.map((r) => ({
      d: String(r.d),
      scout: (r.scout as Record<string, unknown> | null) ?? null,
      risk: (r.risk as Record<string, unknown> | null) ?? null,
      pm: (r.pm as Record<string, unknown> | null) ?? null,
      applied: (r.applied as Record<string, unknown>[]) ?? [],
      errors: (r.errors as string[]) ?? [],
    })),
    deskLessons: deskLessons.map((r) => ({
      lesson: String(r.lesson),
      confidence: Number(r.confidence),
    })),
  }
}

// ── basket writes (used by /api/portfolios/*) ──────────────────────────────

export async function listBaskets(): Promise<{ id: string; name: string }[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT portfolio_id, name FROM atlas_foundation.portfolio_master
    WHERE kind = 'basket' AND status = 'active' ORDER BY name
  `
  return rows.map((r) => ({ id: String(r.portfolio_id), name: String(r.name) }))
}

// Backtest curves for every portfolio, rebased to 100, for the board compare chart.
// Monthly-sampled to keep the payload light; NIFTY 500 included as the benchmark line.
export type CompareCurve = { name: string; category: PortfolioCategory; points: { d: string; v: number }[] }

export async function getCompareCurves(): Promise<CompareCurve[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    WITH m AS (
      SELECT n.portfolio_id, pm.name, pm.origin, pm.kind,
             to_char(n.date, 'YYYY-MM') AS ym, max(n.date) AS d
      FROM atlas_foundation.portfolio_nav_daily n
      JOIN atlas_foundation.portfolio_master pm USING (portfolio_id)
      WHERE n.run_type = 'backtest' AND pm.status = 'active'
      GROUP BY 1, 2, 3, 4, 5
    )
    SELECT m.portfolio_id, m.name, m.origin, m.kind, m.d::text AS d, n.nav
    FROM m JOIN atlas_foundation.portfolio_nav_daily n
      ON n.portfolio_id = m.portfolio_id AND n.run_type = 'backtest' AND n.date = m.d
    ORDER BY m.name, m.d
  `
  const byId = new Map<string, { name: string; category: PortfolioCategory; pts: { d: string; nav: number }[] }>()
  for (const r of rows) {
    const id = String(r.portfolio_id)
    if (!byId.has(id))
      byId.set(id, {
        name: String(r.name),
        category: (r.origin === 'system' ? 'system' : r.kind === 'basket' ? 'basket' : 'rule') as PortfolioCategory,
        pts: [],
      })
    byId.get(id)!.pts.push({ d: String(r.d), nav: Number(r.nav) })
  }
  return [...byId.values()]
    .filter((c) => c.pts.length > 2)
    .map((c) => ({
      name: c.name,
      category: c.category,
      points: c.pts.map((p) => ({ d: p.d, v: (p.nav / c.pts[0].nav) * 100 })),
    }))
}

// A2 leaderboard — straight numbers, no derived comparisons: CAGR / Vol / Sharpe /
// MaxDD / Calmar per book, computed on each book's MEANINGFUL record (backtest for
// strategy portfolios, live for forward-only desks and baskets). NIFTY 500 is just
// another row. The reader compares; the table doesn't editorialize.
export type LeaderboardRow = {
  id: string | null // null = the NIFTY 500 benchmark row
  name: string
  category: PortfolioCategory | 'benchmark'
  isDesk: boolean
  record: string // e.g. "7.5y backtest" | "live 3d"
  blurb: string // one-line what-this-book-does, for the per-row eye icon
  windows: { w1: WindowMetrics; w3: WindowMetrics; w5: WindowMetrics }
  livePct: number | null // since-inception live paper-track, all books
  nPositions: number | null
}

export async function getLeaderboard(): Promise<LeaderboardRow[]> {
  const masters = await sql<Array<Record<string, unknown>>>`
    SELECT m.portfolio_id, m.name, m.kind, m.origin, m.params, m.strategy_key,
           m.asset_classes, m.max_position_pct, ln.n_positions,
           lp.live_pct
    FROM atlas_foundation.portfolio_master m
    LEFT JOIN LATERAL (
      SELECT n_positions FROM atlas_foundation.portfolio_nav_daily
      WHERE portfolio_id = m.portfolio_id AND run_type='live'
      ORDER BY date DESC LIMIT 1) ln ON true
    LEFT JOIN LATERAL (
      SELECT (l.nav / nullif(f.nav, 0) - 1) * 100 AS live_pct
      FROM (SELECT nav FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type='live'
            ORDER BY date ASC LIMIT 1) f,
           (SELECT nav FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type='live'
            ORDER BY date DESC LIMIT 1) l
    ) lp ON true
    WHERE m.status = 'active'
  `
  const series = await sql<Array<Record<string, unknown>>>`
    SELECT portfolio_id::text pid, run_type, date::text d, nav
    FROM atlas_foundation.portfolio_nav_daily ORDER BY date
  `
  const byBook = new Map<string, { d: string; nav: number }[]>()
  for (const r of series) {
    const k = `${r.pid}:${r.run_type}`
    if (!byBook.has(k)) byBook.set(k, [])
    byBook.get(k)!.push({ d: String(r.d), nav: Number(r.nav) })
  }

  const rows: LeaderboardRow[] = masters.map((m) => {
    const pid = String(m.portfolio_id)
    const params = (m.params as Record<string, unknown> | null) ?? null
    const bt = byBook.get(`${pid}:backtest`) ?? []
    const live = byBook.get(`${pid}:live`) ?? []
    const useBt = bt.length > live.length
    const pts = useBt ? bt : live
    const spanDays = pts.length > 1
      ? (new Date(pts[pts.length - 1].d).getTime() - new Date(pts[0].d).getTime()) / 86400000
      : 0
    const record = useBt
      ? `${(spanDays / 365.25).toFixed(1)}y backtest`
      : `live ${Math.round(spanDays)}d`
    const explain = describeStrategy(
      m.kind as 'strategy' | 'basket',
      params,
      (m.asset_classes as string[]) ?? ['stock'],
      Number(m.max_position_pct),
      m.strategy_key ? String(m.strategy_key) : null,
    )
    return {
      id: pid,
      name: String(m.name),
      category: (m.origin === 'system' ? 'system' : m.kind === 'basket' ? 'basket' : 'rule') as PortfolioCategory,
      isDesk: params?.desk === true,
      record,
      blurb: explain ? `${explain.headline}. ${explain.entry}` : 'FM-picked basket.',
      windows: {
        w1: computeWindowMetrics(pts, 1),
        w3: computeWindowMetrics(pts, 3),
        w5: computeWindowMetrics(pts, 5),
      },
      livePct: m.live_pct != null ? Number(m.live_pct) : null,
      nPositions: m.n_positions != null ? Number(m.n_positions) : null,
    }
  })

  // NIFTY 500 over the common backtest span, as a plain row
  const bench = await sql<Array<Record<string, unknown>>>`
    SELECT date::text d, close AS nav FROM atlas_foundation.index_prices
    WHERE index_code = 'NIFTY 500' AND date >= '2019-01-07' ORDER BY date
  `
  const benchPts = bench.map((r) => ({ d: String(r.d), nav: Number(r.nav) }))
  const benchSpan = benchPts.length > 1
    ? (new Date(benchPts[benchPts.length - 1].d).getTime() - new Date(benchPts[0].d).getTime()) / 86400000
    : 0
  rows.push({
    id: null,
    name: 'NIFTY 500',
    category: 'benchmark',
    isDesk: false,
    record: `${(benchSpan / 365.25).toFixed(1)}y index`,
    blurb: 'The NIFTY 500 index itself — the market every book here is trying to beat.',
    windows: {
      w1: computeWindowMetrics(benchPts, 1),
      w3: computeWindowMetrics(benchPts, 3),
      w5: computeWindowMetrics(benchPts, 5),
    },
    livePct: null,
    nPositions: null,
  })

  const rankKey = (r: LeaderboardRow) =>
    r.windows.w5.cagr ?? r.windows.w3.cagr ?? r.windows.w1.cagr ?? (r.livePct != null ? r.livePct / 100 : -9)
  return rows.sort((a, b) => rankKey(b) - rankKey(a))
}

// UI picks are "stock:SYMBOL" / "etf:SYMBOL" / "fund:MSTAR_ID"; the engine keys
// stocks/ETFs by instrument_id uuid. Resolve symbols → uuids; funds pass through.
export async function resolvePicks(
  picks: string[],
): Promise<{ resolved: string[]; unknown: string[] }> {
  const bySymbol = new Map<string, string>() // "class:SYMBOL" → "class:uuid"
  const symbols = picks
    .filter((p) => p.startsWith('stock:') || p.startsWith('etf:'))
    .map((p) => p.split(':', 2)[1])
  if (symbols.length) {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT asset_class, symbol, instrument_id::text AS iid
      FROM atlas_foundation.instrument_master
      WHERE is_active AND asset_class IN ('stock', 'etf') AND symbol = ANY (${symbols})
    `
    for (const r of rows)
      bySymbol.set(`${r.asset_class}:${r.symbol}`, `${r.asset_class}:${r.iid}`)
  }
  const resolved: string[] = []
  const unknown: string[] = []
  for (const p of picks) {
    if (p.startsWith('fund:')) resolved.push(p)
    else if (bySymbol.has(p)) resolved.push(bySymbol.get(p)!)
    else unknown.push(p)
  }
  return { resolved, unknown }
}
