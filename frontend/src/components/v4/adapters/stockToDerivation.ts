// Adapter: a stock's ladder (lens score/decile + sub-components + actual numbers) → the
// canonical ScoreDerivationTree model. Instrument path: Conviction → lens → sub-component →
// underlying variable (leaf). Truthful per the verified scoring model: technical & fundamental
// SUM their sub-component points; catalyst & flow are weighted averages of 0–100 sub-scores.
import type { StockLadder } from './stockToLadder'
import type { DerivRoot, DerivNode } from '@/components/v6/shared/ScoreDerivationTree'

// Composite lens weights (atlas_thresholds.lens_weight_*; valuation/policy = 0). The composite
// (0–100 conviction score) = Σ weight·lens_score, then a convergence boost (≥2 agreeing lenses)
// and a valuation multiplier — so the weighted sum is the BACKBONE, not the exact final value
// (which is read from the DB). TODO(thresholds-panel): read these live so the tree tracks FM edits.
const COMPOSITE_WEIGHTS: { key: string; short: string; w: number }[] = [
  { key: 'technical', short: 'Tech', w: 0.30 },
  { key: 'fundamental', short: 'Fund', w: 0.25 },
  { key: 'flow', short: 'Flow', w: 0.25 },
  { key: 'catalyst', short: 'Cat', w: 0.20 },
]
const TIER_LABEL: Record<string, string> = {
  HIGHEST: 'Highest', HIGH: 'High', MEDIUM: 'Medium', WATCH: 'Watch', BELOW_THRESHOLD: 'Below threshold',
}
const ADDITIVE = new Set(['technical', 'fundamental', 'valuation'])

// sub-component label → {glossary term, keyword(s) to pull its underlying variables from numbers}
const SUB_MAP: Record<string, { term?: string; vars: string[] }> = {
  Trend: { term: 'ema_stack', vars: ['200-EMA', '50-EMA', 'trend stack'] },
  'Rel. strength': { term: 'rs', vars: ['RS vs'] },
  'Vol contraction': { term: 'vol_contraction', vars: ['Bollinger'] },
  Volume: { term: 'volume_ratio', vars: ['Volume vs', 'VWAP'] },
  Profitability: { term: 'roe', vars: ['equity (ROE)', 'capital (ROCE)'] },
  Margin: { term: 'op_margin', vars: ['Operating margin', 'Net margin'] },
  Growth: { vars: ['Revenue growth', 'EPS growth'] },
  'Balance sheet': { term: 'debt_equity', vars: ['Debt'] },
}
// lens key → eye-icon term for the lens itself
const LENS_TERM: Record<string, string | undefined> = {
  valuation: 'pe', flow: 'smart_money',
}

type Sub = { label: string; v: number | null }

// ── evidence readers — surface the ACTUAL drivers the scorer used for catalyst & flow ──
function evNum(v: unknown): number | null {
  if (v == null) return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}
function lensEv(evidence: unknown, key: string): Record<string, unknown> {
  if (!evidence || typeof evidence !== 'object') return {}
  const lenses = (evidence as Record<string, unknown>).lenses
  if (!lenses || typeof lenses !== 'object') return {}
  return ((lenses as Record<string, unknown>)[key] as Record<string, unknown>) ?? {}
}
const signed = (n: number) => `${n >= 0 ? '+' : '−'}${Math.abs(n)}`

// Catalyst: each bucket sub-component → the SPECIFIC filings that scored it (subject + points),
// so "high catalyst because of an order win / acquisition" is visible, not a bare number.
function catalystChildren(evidence: unknown, subs: Sub[]): DerivNode[] {
  const le = lensEv(evidence, 'catalyst')
  const filings = Array.isArray(le.filings) ? (le.filings as Record<string, unknown>[]) : []
  const subScore = (label: string) => subs.find((s) => s.label === label)?.v ?? null
  const BUCKETS: [string, string][] = [['earnings_strategy', 'Earnings'], ['capital_action', 'Capital action'], ['governance', 'Governance']]
  return BUCKETS.map(([bk, label]) => {
    const fs = filings
      .filter((f) => f.bucket === bk)
      .sort((a, b) => Math.abs(evNum(b.weighted) ?? 0) - Math.abs(evNum(a.weighted) ?? 0))
      .slice(0, 6)
    const kids: DerivNode[] = fs.map((f, i) => {
      const w = evNum(f.weighted) ?? 0
      const isOrder = f.category === 'order_win'
      return {
        id: `cat-${bk}-${i}`,
        label: `${String(f.subject ?? 'Filing')}${isOrder ? ' · order win' : ''}`,
        value: signed(w), tone: w > 0 ? 'pos' : w < 0 ? 'neg' : 'neutral',
      }
    })
    return {
      id: `cat-${bk}`, label, score: subScore(label),
      formula: fs.length ? `${label} ${subScore(label)?.toFixed(0) ?? ''} — ${fs.length} scoring filing${fs.length > 1 ? 's' : ''} (most-weighted first)` : undefined,
      children: kids.length ? kids : undefined,
    }
  }).filter((n) => n.score != null || n.children)
}

// Flow: each sub-component → its blend weight + the actual input (promoter %, MF MoM, delivery %).
function flowChildren(evidence: unknown, subs: Sub[]): DerivNode[] {
  const le = lensEv(evidence, 'flow')
  const weights = (le.weights as Record<string, unknown>) ?? {}
  const prom = (le.promoter as Record<string, unknown>) ?? {}
  const sm = (le.smart_money as Record<string, unknown>) ?? {}
  const acc = (le.accumulation as Record<string, unknown>) ?? {}
  const subScore = (label: string) => subs.find((s) => s.label === label)?.v ?? null
  const wpct = (k: string) => { const w = evNum(weights[k]); return w == null ? null : w * 100 }
  const out: DerivNode[] = []
  // Promoter
  const promKids: DerivNode[] = []
  const ppct = evNum(prom.promoter_pct); if (ppct != null) promKids.push({ id: 'flow-prom-pct', label: 'Promoter holding', value: `${ppct.toFixed(1)}%` })
  const ptc = evNum(prom.transaction_count); if (ptc) promKids.push({ id: 'flow-prom-tc', label: 'Insider transactions', value: `${ptc}` })
  out.push({ id: 'flow-promoter', label: 'Promoter', score: subScore('Promoter'), weightPct: wpct('promoter'), children: promKids.length ? promKids : undefined })
  // Smart money (MF / institutional signals)
  const sigs = Array.isArray(sm.signals) ? (sm.signals as string[]) : []
  const smKids: DerivNode[] = sigs.map((s, i) => { const [k, vv] = s.split('='); return { id: `flow-sm-${i}`, label: k.replace(/_/g, ' '), value: vv ?? s } })
  out.push({ id: 'flow-smart', label: 'Smart money', score: subScore('Smart money'), weightPct: wpct('smart_money'), children: smKids.length ? smKids : undefined })
  // Accumulation (delivery)
  const accKids: DerivNode[] = []
  const d30 = evNum(acc.delivery_30d ?? acc.delivery_avg_30d ?? acc.delivery)
  if (d30 != null) accKids.push({ id: 'flow-acc-d', label: 'Delivery · 30d avg', value: `${d30.toFixed(0)}%` })
  else if (typeof acc.reason === 'string') accKids.push({ id: 'flow-acc-r', label: 'Delivery', value: String(acc.reason) })
  out.push({ id: 'flow-acc', label: 'Accumulation (delivery)', score: subScore('Accumulation (delivery)'), weightPct: wpct('accumulation'), children: accKids.length ? accKids : undefined })
  // any remaining sub (e.g. Institutional) with a score but no separate evidence block
  for (const s of subs) if (!out.some((o) => o.label === s.label) && s.v != null) out.push({ id: `flow-${s.label}`, label: s.label, score: s.v })
  return out
}

export function stockToDerivation(symbol: string, name: string | null, ladder: StockLadder): DerivRoot {
  const strength = ladder.strength

  const lenses: DerivNode[] = ladder.lenses.map((l) => {
    const additive = ADDITIVE.has(l.key)
    const subs = l.subs ?? []
    const numbers = l.numbers ?? []
    let children: DerivNode[]
    if (l.key === 'catalyst') {
      // catalyst: the specific filings that scored each bucket (the real events).
      children = catalystChildren(ladder.evidence, subs)
    } else if (l.key === 'flow') {
      // flow: each sub-component's blend weight + its actual input (delivery, MF flow, promoter).
      children = flowChildren(ladder.evidence, subs)
    } else {
      // technical / fundamental / valuation: sub-component → its underlying variables (actual numbers).
      const subNodes: DerivNode[] = subs.map((s) => {
        const m = SUB_MAP[s.label]
        const kids: DerivNode[] = (m?.vars ?? [])
          .flatMap((kw) => numbers.filter((nm) => nm.label.includes(kw)))
          .map((nm) => ({ id: `${l.key}-${s.label}-${nm.label}`, label: nm.label, value: nm.value, tone: nm.tone }))
        return {
          id: `${l.key}-${s.label}`,
          label: s.label,
          score: s.v,
          term: m?.term,
          children: kids.length ? kids : undefined,
        }
      })
      // any actual numbers not already mapped under a sub-component → an "Underlying inputs" node
      const mappedLabels = new Set(subNodes.flatMap((sn) => (sn.children ?? []).map((k) => k.label)))
      const leftover = numbers.filter((nm) => !mappedLabels.has(nm.label))
      children = [...subNodes]
      if (leftover.length) {
        children.push({
          id: `${l.key}-inputs`, label: 'Underlying inputs',
          children: leftover.map((nm) => ({ id: `${l.key}-in-${nm.label}`, label: nm.label, value: nm.value, tone: nm.tone })),
        })
      }
    }
    return {
      id: l.key,
      label: l.label,
      decile: l.decile,
      score: l.score,
      term: LENS_TERM[l.key],
      formula: additive
        ? `${l.label} ${l.score?.toFixed(0) ?? '—'} = sum of sub-component points below`
        : `${l.label} ${l.score?.toFixed(0) ?? '—'} = weighted average of the 0–100 sub-scores below`,
      children: children.length ? children : undefined,
    }
  })

  // Conviction-score breakdown: the real 0–100 composite + tier as the headline, with each
  // conviction lens's weighted contribution (lens score × weight) shown so the number is glass-box.
  const scoreByKey = new Map(ladder.lenses.map((l) => [l.key, l.score]))
  const contribs = COMPOSITE_WEIGHTS.map((c) => ({ ...c, score: scoreByKey.get(c.key) ?? null }))
    .filter((c): c is typeof c & { score: number } => c.score != null)
  const composite = ladder.composite
  const tier = ladder.conviction_tier
  // build the contribution breakdown node: composite ← Σ (lens score × weight)
  const convictionNode: DerivNode | null = composite != null
    ? {
        id: 'conviction-score',
        label: 'Conviction score',
        score: composite,
        formula: `Conviction ${composite.toFixed(0)}/100${tier ? ` · ${TIER_LABEL[tier] ?? tier}` : ''} = Σ (lens score × weight), then ×convergence/valuation`,
        children: contribs.length
          ? contribs.map((c) => ({
              id: `contrib-${c.key}`,
              label: `${c.short} · weight ${c.w.toFixed(2)}`,
              value: `${c.score.toFixed(0)} → ${(c.score * c.w).toFixed(1)}`,
              tone: 'neutral' as const,
            }))
          : undefined,
      }
    : null

  const headline = composite != null
    ? {
        label: tier ? `Conviction score · ${TIER_LABEL[tier] ?? tier}` : 'Conviction score',
        value: `${composite.toFixed(0)}`,
        decile: Math.max(1, Math.min(10, Math.round(composite / 10))),
      }
    : { label: 'Conviction', value: strength != null ? `${strength.toFixed(1)}/10` : '—', decile: strength != null ? Math.round(strength) : null }

  return {
    title: name ? `${symbol} · ${name}` : symbol,
    headline,
    formula: composite != null
      ? `Conviction score ${composite.toFixed(0)}/100 · avg-decile strength ${strength != null ? strength.toFixed(1) : '—'}/10`
      : '= 0.30·Tech + 0.25·Fund + 0.25·Flow + 0.20·Cat',
    lenses: convictionNode ? [convictionNode, ...lenses] : lenses,
  }
}
