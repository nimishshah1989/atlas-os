// frontend/src/lib/queries/v6/calls-performance.ts
//
// Reads atlas.mv_calls_performance — one row per signal call (in-flight or
// closed) with predicted vs realized excess return. Derives summary stats
// (hit rate, avg excess, status counts) on the way out.
//
// MV refreshed nightly via pg_cron (Phase D).

import 'server-only'
import sql from '@/lib/db'

export type CallRow = {
  signal_call_id: string
  instrument_id: string
  symbol: string
  company_name: string
  cell_name: string | null
  cap_tier: string | null
  tenure: string | null
  action: string | null
  entry_date: string | null
  confidence_unconditional: number | null
  predicted_excess: number | null
  stock_ret_pct: number | null
  bench_ret_pct: number | null
  realized_excess_pct: number | null
  days_in_position: number
  is_hit: boolean
  status: string
  refreshed_at: string | null
}

export type CallsSummary = {
  total: number
  hits: number
  hit_rate: number | null
  avg_realized_excess_pct: number | null
  by_status: Record<string, number>
}

export type CallsPerformancePage = {
  calls: CallRow[]
  summary: CallsSummary
}

type Row = Omit<
  CallRow,
  | 'confidence_unconditional' | 'predicted_excess'
  | 'stock_ret_pct' | 'bench_ret_pct' | 'realized_excess_pct'
  | 'days_in_position'
> & {
  confidence_unconditional: string | null
  predicted_excess: string | null
  stock_ret_pct: string | null
  bench_ret_pct: string | null
  realized_excess_pct: string | null
  days_in_position: number | string
}

function toNumber(s: string | number | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

function toInt(s: number | string | null | undefined): number {
  if (s == null) return 0
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : 0
}

export async function getCallsPerformancePage(): Promise<CallsPerformancePage> {
  const rows = await sql<Row[]>`
    SELECT
      signal_call_id, instrument_id, symbol, company_name,
      cell_name, cap_tier, tenure, action,
      entry_date::text                       AS entry_date,
      confidence_unconditional::text         AS confidence_unconditional,
      predicted_excess::text                 AS predicted_excess,
      stock_ret_pct::text                    AS stock_ret_pct,
      bench_ret_pct::text                    AS bench_ret_pct,
      realized_excess_pct::text              AS realized_excess_pct,
      days_in_position, is_hit, status,
      refreshed_at::text                     AS refreshed_at
    FROM atlas.mv_calls_performance
    ORDER BY entry_date DESC NULLS LAST, symbol
  `

  const calls: CallRow[] = rows.map(r => ({
    signal_call_id: r.signal_call_id,
    instrument_id: r.instrument_id,
    symbol: r.symbol,
    company_name: r.company_name,
    cell_name: r.cell_name,
    cap_tier: r.cap_tier,
    tenure: r.tenure,
    action: r.action,
    entry_date: r.entry_date,
    confidence_unconditional: toNumber(r.confidence_unconditional),
    predicted_excess: toNumber(r.predicted_excess),
    stock_ret_pct: toNumber(r.stock_ret_pct),
    bench_ret_pct: toNumber(r.bench_ret_pct),
    realized_excess_pct: toNumber(r.realized_excess_pct),
    days_in_position: toInt(r.days_in_position),
    is_hit: r.is_hit,
    status: r.status,
    refreshed_at: r.refreshed_at,
  }))

  const total = calls.length
  const hits = calls.reduce((acc, c) => acc + (c.is_hit ? 1 : 0), 0)
  const hit_rate = total > 0 ? hits / total : null

  const realizedValues = calls
    .map(c => c.realized_excess_pct)
    .filter((v): v is number => v != null)
  const avg_realized_excess_pct = realizedValues.length > 0
    ? realizedValues.reduce((a, b) => a + b, 0) / realizedValues.length
    : null

  const by_status: Record<string, number> = {}
  for (const c of calls) {
    by_status[c.status] = (by_status[c.status] ?? 0) + 1
  }

  return {
    calls,
    summary: { total, hits, hit_rate, avg_realized_excess_pct, by_status },
  }
}
