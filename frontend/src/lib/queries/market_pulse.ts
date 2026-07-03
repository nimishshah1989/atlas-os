// src/lib/queries/market_pulse.ts
// Native Markets-Today tables — all from atlas_foundation (no atlas.* dependency):
//  - getTierReturns(): SC/MC/LC tier returns + spreads across windows (from index_prices)
//  - getMacroContext(): macro context table (from atlas_macro_daily, mirrored)
//  - getBreadthTable(): the detailed 9-row breadth table (from atlas_market_regime_daily, mirrored)
import 'server-only'
import sql from '@/lib/db'

// ── Tier returns (SC 250 / MC 150 / LC = Nifty 100) ───────────────────────
export type TierWindow = {
  label: string
  sc: number | null
  mc: number | null
  lc: number | null
  sc_lc: number | null // SC − LC spread (pp, as fraction)
  mc_lc: number | null // MC − LC spread
}
export type TierReturns = { windows: TierWindow[]; smallcap_rs_z: number | null }

const TIER_CODES = { lc: 'NIFTY 100', mc: 'NIFTY MIDCAP 150', sc: 'NIFTY SMLCAP 250' }
// rn=1 latest; offsets ~ trading sessions back for 1W/1M/3M/6M/1Y
const OFFS: [string, number][] = [['1W', 6], ['1M', 22], ['3M', 64], ['6M', 127], ['1Y', 253]]

export async function getTierReturns(): Promise<TierReturns> {
  const rows = await sql<{ index_code: string; rn: number; close: string }[]>`
    SELECT index_code, close::text,
           row_number() OVER (PARTITION BY index_code ORDER BY date DESC) AS rn
    FROM atlas_foundation.index_prices
    WHERE index_code IN (${TIER_CODES.lc}, ${TIER_CODES.mc}, ${TIER_CODES.sc})
      AND date >= NOW() - INTERVAL '2 years' AND close > 0
  `
  const by: Record<string, Map<number, number>> = {}
  for (const r of rows) (by[r.index_code] ??= new Map()).set(Number(r.rn), parseFloat(r.close))
  const ret = (code: string, off: number): number | null => {
    const m = by[code]; if (!m) return null
    const c0 = m.get(1); const cn = m.get(off)
    return c0 != null && cn != null && cn > 0 ? c0 / cn - 1 : null
  }
  const windows: TierWindow[] = OFFS.map(([label, off]) => {
    const sc = ret(TIER_CODES.sc, off), mc = ret(TIER_CODES.mc, off), lc = ret(TIER_CODES.lc, off)
    return {
      label, sc, mc, lc,
      sc_lc: sc != null && lc != null ? sc - lc : null,
      mc_lc: mc != null && lc != null ? mc - lc : null,
    }
  })
  // smallcap RS z-score: z of (SC ÷ LC) daily ratio over the last ~1y
  const z = await sql<{ z: string | null }[]>`
    WITH r AS (
      SELECT s.date, s.close / l.close AS ratio
      FROM atlas_foundation.index_prices s
      JOIN atlas_foundation.index_prices l ON l.date = s.date AND l.index_code = ${TIER_CODES.lc}
      WHERE s.index_code = ${TIER_CODES.sc} AND s.date >= NOW() - INTERVAL '1 year' AND l.close > 0
    )
    SELECT ((SELECT ratio FROM r ORDER BY date DESC LIMIT 1) - avg(ratio)) / NULLIF(stddev(ratio), 0) AS z
    FROM r
  `.catch(() => [{ z: null }])
  return { windows, smallcap_rs_z: z[0]?.z != null ? parseFloat(z[0].z) : null }
}

// ── Macro context ─────────────────────────────────────────────────────────
export type MacroRow = {
  id: string; label: string; value: number | null; unit: string
  d1: number | null; d1m: number | null
}

export async function getMacroContext(): Promise<{ rows: MacroRow[]; as_of: string | null }> {
  const r = await sql<Record<string, string>[]>`
    SELECT to_char(date,'YYYY-MM-DD') AS date, usdinr, dxy, india_10y_yield, us_10y_yield,
           brent_inr, cpi_yoy, fii_cash_equity_flow_cr, dii_flow
    FROM atlas_foundation.atlas_macro_daily ORDER BY date DESC LIMIT 25
  `
  if (r.length === 0) return { rows: [], as_of: null }
  const num = (v: string | null | undefined) => (v == null ? null : parseFloat(v))
  const at = (i: number, k: string) => num(r[i]?.[k])
  const delta = (k: string, i: number) => {
    const a = at(0, k), b = at(i, k); return a != null && b != null ? a - b : null
  }
  const realYield = (i: number) => {
    // cpi_yoy is 0/missing in the stale macro feed → require a sane CPI (>=1%) before
    // claiming a "real" yield; otherwise show "—" rather than pass the nominal off as real.
    const y = at(i, 'india_10y_yield'), c = at(i, 'cpi_yoy')
    return y != null && c != null && c >= 1 ? y - c : null
  }
  const rows: MacroRow[] = [
    { id: 'usdinr', label: 'USD / INR', value: at(0, 'usdinr'), unit: '', d1: delta('usdinr', 1), d1m: delta('usdinr', 21) },
    { id: 'india_10y', label: 'India 10Y yield', value: at(0, 'india_10y_yield'), unit: '%', d1: delta('india_10y_yield', 1), d1m: delta('india_10y_yield', 21) },
    { id: 'us_10y', label: 'US 10Y yield', value: at(0, 'us_10y_yield'), unit: '%', d1: delta('us_10y_yield', 1), d1m: delta('us_10y_yield', 21) },
    { id: 'real_yield', label: 'Real yield (10Y − CPI)', value: realYield(0), unit: '%', d1: null, d1m: null },
    { id: 'brent_inr', label: 'Brent (INR)', value: at(0, 'brent_inr'), unit: '₹', d1: delta('brent_inr', 1), d1m: delta('brent_inr', 21) },
    { id: 'dxy', label: 'DXY (dollar index)', value: at(0, 'dxy'), unit: '', d1: delta('dxy', 1), d1m: delta('dxy', 21) },
    { id: 'fii', label: 'FII cash (₹cr)', value: at(0, 'fii_cash_equity_flow_cr'), unit: '₹cr', d1: null, d1m: null },
    { id: 'dii', label: 'DII flow (₹cr)', value: at(0, 'dii_flow'), unit: '₹cr', d1: null, d1m: null },
  ]
  return { rows, as_of: r[0]?.date ?? null }
}

// ── Detailed breadth table (9 rows) ───────────────────────────────────────
export type BreadthTableRow = {
  metric: string; label: string; kind: 'pct' | 'count' | 'ratio' | 'signed'
  today: number | null; d1w: number | null; d1m: number | null
}

export async function getBreadthTable(): Promise<{ rows: BreadthTableRow[]; as_of: string | null }> {
  const r = await sql<Record<string, string>[]>`
    SELECT to_char(date,'YYYY-MM-DD') AS date, pct_above_ema_20, pct_above_ema_50,
           pct_above_ema_100, pct_above_ema_200, new_52w_highs, new_52w_lows,
           ad_ratio, mcclellan_oscillator, ad_line
    FROM atlas_foundation.atlas_market_regime_daily
    WHERE pct_above_ema_50 IS NOT NULL ORDER BY date DESC LIMIT 25
  `
  if (r.length === 0) return { rows: [], as_of: null }
  const num = (v: string | null | undefined) => (v == null ? null : parseFloat(v))
  const at = (i: number, k: string) => num(r[i]?.[k])
  const d = (k: string, i: number) => { const a = at(0, k), b = at(i, k); return a != null && b != null ? a - b : null }
  const mk = (metric: string, label: string, kind: BreadthTableRow['kind']): BreadthTableRow => ({
    metric, label, kind, today: at(0, metric), d1w: d(metric, 5), d1m: d(metric, 21),
  })
  const rows: BreadthTableRow[] = [
    mk('pct_above_ema_20', '% above 20-EMA', 'pct'),
    mk('pct_above_ema_50', '% above 50-EMA', 'pct'),
    mk('pct_above_ema_100', '% above 100-EMA', 'pct'),
    mk('pct_above_ema_200', '% above 200-EMA', 'pct'),
    mk('new_52w_highs', 'New 52-wk highs', 'count'),
    mk('new_52w_lows', 'New 52-wk lows', 'count'),
    mk('ad_ratio', 'A/D ratio', 'ratio'),
    mk('mcclellan_oscillator', 'McClellan oscillator', 'signed'),
    mk('ad_line', 'A/D line (cumulative)', 'signed'),
  ]
  return { rows, as_of: r[0]?.date ?? null }
}

// ── Sector performance — for each sector, the NSE index ÷ NIFTY 50 relative-trend series
// (~65 sessions; building vs fading) PLUS the sector index's own 1w/1m return. All computed
// straight from index_prices (the mv_sector_cards.ret_* columns are a known bad source —
// duplicated rows + impossible values — so we don't use them here). One batched query. ──
export type SectorPerf = { spark: number[]; ret_1w: number | null; ret_1m: number | null }
export async function getSectorPerf(): Promise<Record<string, SectorPerf>> {
  const rows = await sql<Array<{ sector_name: string; idx_close: string; ratio: string }>>`
    WITH n50 AS (
      SELECT date, close FROM atlas_foundation.index_prices
      WHERE index_code = 'NIFTY 50' AND date >= CURRENT_DATE - 110 AND close > 0
    )
    SELECT sm.sector_name, ip.close::text AS idx_close, (ip.close / n.close)::text AS ratio
    FROM atlas_foundation.atlas_sector_master sm
    JOIN atlas_foundation.index_prices ip
      ON ip.index_code = sm.primary_nse_index AND ip.date >= CURRENT_DATE - 110 AND ip.close > 0
    JOIN n50 n ON n.date = ip.date
    WHERE sm.is_active
    ORDER BY sm.sector_name, ip.date
  `
  const ratios: Record<string, number[]> = {}
  const closes: Record<string, number[]> = {}
  for (const r of rows) {
    const ra = Number(r.ratio), cl = Number(r.idx_close)
    if (Number.isFinite(ra)) (ratios[r.sector_name] ??= []).push(ra)
    if (Number.isFinite(cl)) (closes[r.sector_name] ??= []).push(cl)
  }
  const ret = (s: number[], k: number) => (s.length > k && s[s.length - 1 - k] ? (s[s.length - 1] - s[s.length - 1 - k]) / s[s.length - 1 - k] * 100 : null)
  const out: Record<string, SectorPerf> = {}
  for (const k of Object.keys(ratios)) {
    out[k] = { spark: ratios[k].slice(-65), ret_1w: ret(closes[k] ?? [], 5), ret_1m: ret(closes[k] ?? [], 21) }
  }
  return out
}

// ── Broad-market index strip — latest level + 1d / 1w / 1m % change for the headline
// indices, so the page opens with "where the market is" at a glance. ──
export type IndexQuote = { code: string; label: string; close: number | null; d1: number | null; d1w: number | null; d1m: number | null }
const STRIP: Array<[string, string]> = [
  ['NIFTY 50', 'Nifty 50'], ['NIFTY BANK', 'Bank Nifty'],
  ['NIFTY MIDCAP 150', 'Midcap 150'], ['NIFTY SMLCAP 250', 'Smallcap 250'],
]
export async function getIndexStrip(): Promise<IndexQuote[]> {
  const rows = await sql<Array<{ index_code: string; date: string; close: string }>>`
    SELECT index_code, to_char(date,'YYYY-MM-DD') AS date, close::text
    FROM atlas_foundation.index_prices
    WHERE index_code = ANY(${STRIP.map((s) => s[0])}) AND close > 0
      AND date >= CURRENT_DATE - 60
    ORDER BY index_code, date
  `
  const byCode = new Map<string, number[]>()
  for (const r of rows) {
    const v = Number(r.close)
    if (Number.isFinite(v)) (byCode.get(r.index_code) ?? byCode.set(r.index_code, []).get(r.index_code)!).push(v)
  }
  const chg = (s: number[], k: number) => (s.length > k && s[s.length - 1 - k] ? (s[s.length - 1] - s[s.length - 1 - k]) / s[s.length - 1 - k] * 100 : null)
  return STRIP.map(([code, label]) => {
    const s = byCode.get(code) ?? []
    return { code, label, close: s.length ? s[s.length - 1] : null, d1: chg(s, 1), d1w: chg(s, 5), d1m: chg(s, 21) }
  })
}
