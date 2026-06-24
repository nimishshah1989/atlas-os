// Adapter: a stock's StockDecile + StockEvidence → the generic DecileLadder model.
// All stock-specific "real numbers" logic lives here (ported from the
// StockLensCardV4 seed) so DecileLadder itself stays dumb + reusable. RULE #0:
// every value traces to a real foundation_staging field — no synthetic fallback.
import type { StockDecile, StockEvidence } from '@/lib/queries/v6/stock_lens'
import type { LadderLens, LadderNumber } from '../ui/DecileLadder'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }

// units (from the stock_lens recon): RS fields are FRACTIONS (×100 for display);
// delivery / promoter / pos_52w / dist_ema are already PERCENT; vol_ratio is ×.
function lensNumbers(key: string, ev: StockEvidence | null): LadderNumber[] {
  if (!ev) return []
  const pct = (v: number | null, d = 1): string => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`)
  const tone = (v: number | null): LadderNumber['tone'] => (v == null ? 'neutral' : v >= 0 ? 'pos' : 'neg')
  const x = (v: number | null, suffix = '', d = 1) => (v == null ? '—' : `${v.toFixed(d)}${suffix}`)
  switch (key) {
    case 'technical':
      return [
        { label: 'Price vs 200-EMA', value: pct(ev.dist_ema200), tone: tone(ev.dist_ema200) },
        { label: 'Price vs 50-EMA', value: pct(ev.dist_ema50), tone: tone(ev.dist_ema50) },
        { label: 'RSI(14)', value: x(ev.rsi, '', 0) },
        { label: 'RS vs Nifty 500 · 3M', value: pct(ev.rs_3m == null ? null : ev.rs_3m * 100), tone: tone(ev.rs_3m) },
        { label: 'RS vs sector · 3M', value: pct(ev.rs_sector_3m == null ? null : ev.rs_sector_3m * 100), tone: tone(ev.rs_sector_3m) },
        { label: '52-week range', value: x(ev.pos_52w, '%', 0) },
        { label: 'Volume vs 30d avg', value: x(ev.vol_ratio_30d, '×', 2) },
        { label: 'Bollinger-band width', value: x(ev.bb_width, '', 3) },
      ]
    case 'flow':
      return [
        { label: 'Delivery (today)', value: x(ev.delivery_pct, '%') },
        { label: 'Delivery · 30d avg', value: x(ev.delivery_30d, '%') },
        { label: 'Delivery · 60d avg', value: x(ev.delivery_60d, '%') },
        { label: 'Up/down-day asymmetry', value: x(ev.delivery_asym, 'pp'), tone: tone(ev.delivery_asym) },
        { label: 'Promoter holding', value: x(ev.promoter_pct, '%') },
      ]
    case 'valuation':
      return [
        { label: 'P/E (TTM)', value: x(ev.pe_ttm, '×') },
        { label: 'TTM EPS', value: ev.eps_ttm == null ? '—' : `₹${ev.eps_ttm.toFixed(1)}` },
        { label: '52-week range', value: x(ev.pos_52w, '%', 0) },
      ]
    default:
      return [] // fundamental → 8-quarter table; catalyst → announcements panel
  }
}

const POINTER: Record<string, string> = {
  fundamental: 'Real numbers in the 8-quarter financials table on the stock page.',
  catalyst: 'Real filings in the corporate-announcements panel on the stock page.',
}

// Pull human-readable evidence strings out of the journal `evidence` JSONB for a
// lens. Shape varies by pipeline; defensively read common containers. No
// synthetic fallback — absence is rendered as absence.
function evidenceFor(evidence: unknown, lensKey: string): string[] {
  if (!evidence || typeof evidence !== 'object') return []
  const e = evidence as Record<string, unknown>
  const out: string[] = []
  const collect = (val: unknown) => {
    if (typeof val === 'string') {
      if (val.trim()) out.push(val.trim())
      return
    }
    if (Array.isArray(val)) {
      for (const v of val) collect(v)
      return
    }
    if (val && typeof val === 'object') {
      const o = val as Record<string, unknown>
      for (const k of ['label', 'text', 'reason', 'detail', 'driver', 'note', 'summary']) {
        if (typeof o[k] === 'string' && (o[k] as string).trim()) out.push((o[k] as string).trim())
      }
    }
  }
  collect(e[lensKey])
  for (const k of ['drivers', 'reasons', 'notes', 'highlights']) {
    const c = e[k]
    if (c && typeof c === 'object' && !Array.isArray(c)) collect((c as Record<string, unknown>)[lensKey])
  }
  return Array.from(new Set(out)).slice(0, 4)
}

export type StockLadder = {
  lenses: LadderLens[]
  strength: number | null
  leadership: { n: number; of: number }
  cohortLabel: string
  topLensKey: string | null
}

export function stockToLadder(decile: StockDecile, ev: StockEvidence | null): StockLadder {
  const lenses: LadderLens[] = decile.lens.map((l) => ({
    key: l.key,
    label: l.label,
    decile: l.decile,
    score: l.score,
    numbers: lensNumbers(l.key, ev),
    subs: l.subs.filter((s) => s.v != null) as { label: string; v: number }[],
    evidence: evidenceFor(decile.evidence, l.key),
    pointer: POINTER[l.key],
  }))
  // top lens = highest decile (ties → first); used to auto-open the showcase row.
  const topLensKey = lenses
    .filter((l) => l.decile != null)
    .sort((a, b) => (b.decile! - a.decile!))[0]?.key ?? lenses[0]?.key ?? null
  return {
    lenses,
    strength: decile.strength,
    leadership: { n: decile.lead, of: 4 },
    cohortLabel: CAP_LABEL[decile.cap] ?? decile.cap,
    topLensKey,
  }
}
