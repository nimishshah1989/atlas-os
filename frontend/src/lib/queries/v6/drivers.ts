// Per-constituent lens DRIVERS — the one-line "what actually drove this lens" for a stock, pulled
// from its stored evidence. Lets a sector / ETF / fund score-tree show, under each lens, WHICH
// constituent drove it and WHY (its top catalyst filing, its flow input, its RS, its ROE) — the
// names link to their own /stocks page for the full derivation. RULE #0: every driver is read from
// the real evidence JSONB; absent → null (never invented).
import 'server-only'
import sql from '@/lib/db'

export type LensDrivers = {
  technical: string | null
  fundamental: string | null
  catalyst: string | null
  flow: string | null
}

const num = (v: unknown): number | null => {
  if (v == null) return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {})
const signed = (n: number, d = 0) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(d)}`

// Catalyst → the single most-weighted scoring filing (the real event: order win, acquisition, …).
function catalystDriver(le: Record<string, unknown>): string | null {
  const filings = Array.isArray(le.filings) ? (le.filings as Record<string, unknown>[]) : []
  if (!filings.length) return null
  const top = [...filings].sort((a, b) => Math.abs(num(b.weighted) ?? 0) - Math.abs(num(a.weighted) ?? 0))[0]
  const w = num(top.weighted) ?? 0
  if (w === 0) return null
  const order = top.category === 'order_win' ? ' (order win)' : ''
  return `${String(top.subject ?? 'Filing')}${order} ${signed(w)}`
}

// Flow → the strongest input behind the score: MF-flow signal, else promoter holding, else delivery.
function flowDriver(le: Record<string, unknown>): string | null {
  const sm = obj(le.smart_money)
  const sigs = Array.isArray(sm.signals) ? (sm.signals as string[]) : []
  const mf = sigs.find((s) => s.startsWith('mf_mom_delta'))
  if (mf) return `MF MoM ${mf.split('=')[1] ?? ''}`
  const prom = obj(le.promoter)
  const pp = num(prom.promoter_pct)
  if (pp != null) return `Promoter ${pp.toFixed(0)}%`
  const acc = obj(le.accumulation)
  const d = num(acc.delivery_30d ?? acc.delivery_avg_30d ?? acc.delivery)
  if (d != null) return `Delivery ${d.toFixed(0)}%`
  return null
}

function technicalDriver(le: Record<string, unknown>): string | null {
  const rs = num(obj(le.relative_strength).rs_n500)
  return rs == null ? null : `RS ${signed(rs * 100)}%`
}
function fundamentalDriver(le: Record<string, unknown>): string | null {
  const roe = num(obj(le.profitability).roe)
  return roe == null ? null : `ROE ${roe.toFixed(0)}%`
}

function extract(evidence: unknown): LensDrivers {
  let ev: unknown = evidence
  if (typeof ev === 'string') { try { ev = JSON.parse(ev) } catch { ev = null } }
  const lenses = obj(obj(ev).lenses)
  return {
    technical: technicalDriver(obj(lenses.technical)),
    fundamental: fundamentalDriver(obj(lenses.fundamental)),
    catalyst: catalystDriver(obj(lenses.catalyst)),
    flow: flowDriver(obj(lenses.flow)),
  }
}

// Drivers for a set of constituent symbols (latest snapshot), keyed by symbol.
export async function getConstituentDrivers(symbols: string[]): Promise<Record<string, LensDrivers>> {
  const uniq = Array.from(new Set(symbols.filter(Boolean)))
  if (uniq.length === 0) return {}
  const rows = await sql<{ symbol: string; evidence: unknown }[]>`
    SELECT im.symbol, l.evidence
    FROM foundation_staging.atlas_lens_scores_daily l
    JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
    WHERE l.asset_class = 'stock'
      AND l.date = (SELECT max(date) FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock')
      AND im.symbol = ANY(${uniq})
  `
  const out: Record<string, LensDrivers> = {}
  for (const r of rows) out[r.symbol] = extract(r.evidence)
  return out
}
