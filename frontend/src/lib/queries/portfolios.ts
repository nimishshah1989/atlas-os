// Portfolio board data — atlas_foundation.portfolio_* ONLY. Holdings are DERIVED
// from the immutable trade log (no positions table); NAV/backtest series come from
// portfolio_nav_daily written by scripts/foundation/portfolio_run.py. RULE #0: every
// number is a stored engine output or a stored market price — nothing derived here
// beyond joins and percentages.
import 'server-only'
import sql from '@/lib/db'

export type PortfolioSummary = {
  id: string
  name: string
  kind: 'strategy' | 'basket'
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
}

const strategyLabel = (key: string | null, params: Record<string, unknown> | null) =>
  key === 'ema_cross' && params ? `EMA ${params.fast}/${params.slow} crossover` : key

export async function getPortfolios(): Promise<PortfolioSummary[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT m.portfolio_id, m.name, m.kind, m.strategy_key, m.params, m.asset_classes,
           m.initial_capital, m.max_position_pct, m.inception_date::text AS inception_date,
           ln.date::text AS nav_date, ln.nav, ln.cash, ln.n_positions,
           bt.total_pct AS bt_total_pct, bt.years AS bt_years
    FROM atlas_foundation.portfolio_master m
    LEFT JOIN LATERAL (
      SELECT date, nav, cash, n_positions FROM atlas_foundation.portfolio_nav_daily n
      WHERE n.portfolio_id = m.portfolio_id AND n.run_type = 'live'
      ORDER BY date DESC LIMIT 1
    ) ln ON true
    LEFT JOIN LATERAL (
      SELECT (l.nav / nullif(f.nav, 0) - 1) * 100 AS total_pct,
             (l.date - f.date) / 365.25 AS years
      FROM (SELECT nav, date FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type = 'backtest'
            ORDER BY date ASC LIMIT 1) f,
           (SELECT nav, date FROM atlas_foundation.portfolio_nav_daily
            WHERE portfolio_id = m.portfolio_id AND run_type = 'backtest'
            ORDER BY date DESC LIMIT 1) l
    ) bt ON true
    WHERE m.status = 'active'
    ORDER BY m.created_at
  `
  return rows.map((r) => ({
    id: String(r.portfolio_id),
    name: String(r.name),
    kind: r.kind as 'strategy' | 'basket',
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
}

export type NavPointRow = { d: string; nav: number }
export type TradeRow = {
  date: string
  symbol: string
  side: string
  qty: number
  price: number
  value: number
  reason: string
  runType: string
}

export type PortfolioDetail = {
  summary: PortfolioSummary
  holdings: Holding[]
  liveNav: NavPointRow[]
  backtestNav: NavPointRow[]
  benchmark: NavPointRow[] // NIFTY 500 close over the backtest window
  trades: TradeRow[]
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
  const holdings: Holding[] = pos
    .map((r) => {
      const k = String(r.instrument_key)
      const price = lastPrice.get(k) ?? null
      const qty = Number(r.qty)
      const m = meta.get(k)
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
      }
    })
    .sort((a, b) => (b.value ?? -1) - (a.value ?? -1))
  const nav = (runType: string) => sql<Array<Record<string, unknown>>>`
    SELECT date::text AS d, nav FROM atlas_foundation.portfolio_nav_daily
    WHERE portfolio_id = ${id} AND run_type = ${runType} ORDER BY date
  `
  const [liveNav, backtestNav] = await Promise.all([nav('live'), nav('backtest')])
  const btStart = backtestNav[0]?.d ?? summary.inceptionDate
  const benchmark = await sql<Array<Record<string, unknown>>>`
    SELECT date::text AS d, close AS nav FROM atlas_foundation.index_prices
    WHERE index_code = 'NIFTY 500' AND date >= ${String(btStart)} ORDER BY date
  `
  const trades = await sql<Array<Record<string, unknown>>>`
    SELECT trade_date::text AS date, symbol, side, qty, price, value, reason, run_type
    FROM atlas_foundation.portfolio_trades
    WHERE portfolio_id = ${id}
    ORDER BY trade_date DESC, trade_id DESC LIMIT 200
  `
  const toNav = (rs: Array<Record<string, unknown>>): NavPointRow[] =>
    rs.map((r) => ({ d: String(r.d), nav: Number(r.nav) }))
  return {
    summary,
    holdings,
    liveNav: toNav(liveNav),
    backtestNav: toNav(backtestNav),
    benchmark: toNav(benchmark),
    trades: trades.map((r) => ({
      date: String(r.date),
      symbol: String(r.symbol),
      side: String(r.side),
      qty: Number(r.qty),
      price: Number(r.price),
      value: Number(r.value),
      reason: String(r.reason),
      runType: String(r.run_type),
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
