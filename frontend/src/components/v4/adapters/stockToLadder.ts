// Adapter: a stock's StockDecile + StockEvidence → the generic DecileLadder model.
// All stock-specific "real numbers" logic lives here (ported from the
// StockLensCardV4 seed) so DecileLadder itself stays dumb + reusable. RULE #0:
// every value traces to a real foundation_staging field — no synthetic fallback.
import type { StockDecile, StockEvidence } from '@/lib/queries/v6/stock_lens'
import type { LadderLens, LadderNumber } from '../ui/DecileLadder'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }

// Pull a numeric value out of the per-lens evidence (scorer stores Decimals as
// strings via json default=str), tolerant of number | string | null.
function num(v: unknown): number | null {
  if (v == null) return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}
function lensEvidence(evidence: unknown, key: string): Record<string, unknown> {
  if (!evidence || typeof evidence !== 'object') return {}
  const lenses = (evidence as Record<string, unknown>).lenses
  if (!lenses || typeof lenses !== 'object') return {}
  return ((lenses as Record<string, unknown>)[key] as Record<string, unknown>) ?? {}
}

// units (from the stock_lens recon): RS fields are FRACTIONS (×100 for display);
// delivery / promoter / pos_52w / dist_ema are already PERCENT; vol_ratio is ×.
// `le` = the per-lens evidence object (evidence.lenses[key]) — carries the REAL
// inputs the scorer used (ROE/ROCE, order-win filings, MF MoM delta, …).
function lensNumbers(key: string, ev: StockEvidence | null, le: Record<string, unknown>): LadderNumber[] {
  const pct = (v: number | null, d = 1): string => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`)
  const pctAbs = (v: number | null, d = 1): string => (v == null ? '—' : `${v.toFixed(d)}%`)
  const tone = (v: number | null): LadderNumber['tone'] => (v == null ? 'neutral' : v >= 0 ? 'pos' : 'neg')
  const x = (v: number | null, suffix = '', d = 1) => (v == null ? '—' : `${v.toFixed(d)}${suffix}`)
  const keep = (ns: LadderNumber[]) => ns.filter((n) => n.value !== '—')
  switch (key) {
    case 'technical': {
      if (!ev) return []
      // 21/50/200-EMA stacking — the textbook trend structure (21>50>200 = up).
      const stack = (ev.ema21 != null && ev.ema50 != null && ev.ema200 != null)
        ? (ev.ema21 > ev.ema50 && ev.ema50 > ev.ema200
            ? { value: 'Up · 21>50>200', tone: 'pos' as const }
            : (ev.ema21 < ev.ema50 && ev.ema50 < ev.ema200
                ? { value: 'Down · 21<50<200', tone: 'neg' as const }
                : { value: 'Mixed', tone: 'neutral' as const }))
        : { value: '—', tone: 'neutral' as const }
      return keep([
        // VWAP distance first — the mean-reversion signal (price tends to revert to its 1-yr VWAP).
        { label: 'Price vs VWAP (1y)', value: pct(ev.vwap_dist), tone: tone(ev.vwap_dist) },
        { label: 'EMA trend stack', value: stack.value, tone: stack.tone },
        { label: 'Price vs 200-EMA', value: pct(ev.dist_ema200), tone: tone(ev.dist_ema200) },
        { label: 'Price vs 50-EMA', value: pct(ev.dist_ema50), tone: tone(ev.dist_ema50) },
        { label: 'RSI(14)', value: x(ev.rsi, '', 0) },
        { label: 'RS vs Nifty 500 · 3M', value: pct(ev.rs_3m == null ? null : ev.rs_3m * 100), tone: tone(ev.rs_3m) },
        { label: 'RS vs sector · 3M', value: pct(ev.rs_sector_3m == null ? null : ev.rs_sector_3m * 100), tone: tone(ev.rs_sector_3m) },
        { label: '52-week range', value: x(ev.pos_52w, '%', 0) },
        { label: 'Volume vs 30d avg', value: x(ev.vol_ratio_30d, '×', 2) },
        { label: 'Volume vs 60d avg', value: x(ev.vol_ratio_60d, '×', 2) },
        { label: 'ATR(14) · volatility', value: x(ev.atr, '', 1) },
        { label: 'Bollinger width · vol contraction', value: x(ev.bb_width, '', 3) },
      ])
    }
    case 'fundamental': {
      // Real inputs the scorer used — Screener.in ready ratios + as-of financials.
      const prof = (le.profitability as Record<string, unknown>) ?? {}
      const marg = (le.margin as Record<string, unknown>) ?? {}
      const grow = (le.growth as Record<string, unknown>) ?? {}
      const bs = (le.balance_sheet as Record<string, unknown>) ?? {}
      return keep([
        { label: 'Return on equity (ROE)', value: pctAbs(num(prof.roe)) },
        { label: 'Return on capital (ROCE)', value: pctAbs(num(prof.roce)) },
        { label: 'Operating margin', value: pctAbs(num(marg.op_margin)) },
        { label: 'Net margin', value: pctAbs(num(marg.net_margin ?? prof.net_margin)) },
        { label: 'Revenue growth · YoY', value: pct(num(grow.revenue_growth)), tone: tone(num(grow.revenue_growth)) },
        { label: 'EPS growth · YoY', value: pct(num(grow.eps_growth)), tone: tone(num(grow.eps_growth)) },
        { label: 'Debt / equity', value: x(num(bs.debt_to_equity), '×', 2) },
      ])
    }
    case 'valuation':
      if (!ev) return []
      return keep([
        { label: 'P/E (TTM)', value: x(ev.pe_ttm, '×') },
        { label: 'TTM EPS', value: ev.eps_ttm == null ? '—' : `₹${ev.eps_ttm.toFixed(1)}` },
        { label: '52-week range', value: x(ev.pos_52w, '%', 0) },
      ])
    case 'catalyst': {
      // Which filings actually moved the score — order wins surfaced explicitly.
      const bt = (le.bucket_totals_raw as Record<string, unknown>) ?? {}
      const filings = (le.filings as Array<Record<string, unknown>>) ?? []
      const ow = filings.filter((f) => f.category === 'order_win')
      const owPts = ow.reduce((s, f) => s + (num(f.weighted) ?? 0), 0)
      return keep([
        ...(ow.length ? [{ label: `Order wins · ${ow.length} filings`, value: `+${owPts.toFixed(0)}`, tone: 'pos' as const }] : []),
        { label: 'Earnings & momentum', value: x(num(bt.earnings_strategy), '', 0) },
        { label: 'Capital actions', value: x(num(bt.capital_action), '', 0) },
        { label: 'Governance', value: x(num(bt.governance), '', 0) },
      ])
    }
    case 'flow': {
      const sm = (le.smart_money as Record<string, unknown>) ?? {}
      const signals = (sm.signals as string[]) ?? []
      const mf = signals.find((s) => s.startsWith('mf_mom_delta'))
      const mfVal = mf ? num(mf.split('=')[1]?.replace('pp', '')) : null
      return keep([
        { label: 'Promoter holding', value: ev ? x(ev.promoter_pct, '%') : '—' },
        { label: 'MF flow · MoM (matched funds)', value: mfVal == null ? '—' : `${mfVal >= 0 ? '+' : ''}${mfVal.toFixed(1)}pp`, tone: tone(mfVal) },
        { label: 'Delivery · 30d avg', value: ev ? x(ev.delivery_30d, '%') : '—' },
        { label: 'Up/down-day asymmetry', value: ev ? x(ev.delivery_asym, 'pp') : '—', tone: tone(ev?.delivery_asym ?? null) },
      ])
    }
    default:
      return []
  }
}

// Both fundamental and catalyst now carry real numbers inline; the pointers stay as
// "see also" links to the deeper panels, not as the only source.
const POINTER: Record<string, string> = {
  fundamental: 'Full 8-quarter history in the financials table below.',
  catalyst: 'Every filing in the corporate-announcements panel below.',
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
  // The scorer persists structured per-lens evidence under e.lenses[lensKey].
  const lenses = e.lenses
  if (lenses && typeof lenses === 'object') collect((lenses as Record<string, unknown>)[lensKey])
  for (const k of ['drivers', 'reasons', 'notes', 'highlights']) {
    const c = e[k]
    if (c && typeof c === 'object' && !Array.isArray(c)) collect((c as Record<string, unknown>)[lensKey])
  }
  return Array.from(new Set(out)).slice(0, 4)
}

export type StockLadder = {
  lenses: LadderLens[]
  strength: number | null
  composite: number | null
  conviction_tier: string | null
  leadership: { n: number; of: number }
  cohortLabel: string
  topLensKey: string | null
  evidence: unknown   // raw per-lens evidence JSONB → catalyst filings + flow inputs for the score tree
}

export function stockToLadder(decile: StockDecile, ev: StockEvidence | null): StockLadder {
  // Policy is NOT a scored conviction lens (FM 2026-06-26): it carries no decile/score in
  // the ladder — it surfaces as a RAG sector-policy ALERT (PolicyAlertPanel) instead. Drop
  // it here so the "30, no detail" policy row never renders.
  const lenses: LadderLens[] = decile.lens.filter((l) => l.key !== 'policy').map((l) => ({
    key: l.key,
    label: l.label,
    decile: l.decile,
    score: l.score,
    numbers: lensNumbers(l.key, ev, lensEvidence(decile.evidence, l.key)),
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
    composite: decile.composite,
    conviction_tier: decile.conviction_tier,
    leadership: { n: decile.lead, of: 4 },
    cohortLabel: CAP_LABEL[decile.cap] ?? decile.cap,
    topLensKey,
    evidence: decile.evidence,
  }
}
