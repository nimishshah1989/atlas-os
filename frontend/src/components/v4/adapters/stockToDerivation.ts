// Adapter: a stock's ladder (lens score/decile + sub-components + actual numbers) → the
// canonical ScoreDerivationTree model. Instrument path: Conviction → lens → sub-component →
// underlying variable (leaf). Truthful per the verified scoring model: technical & fundamental
// SUM their sub-component points; catalyst & flow are weighted averages of 0–100 sub-scores.
import type { StockLadder } from './stockToLadder'
import type { DerivRoot, DerivNode } from '@/components/v6/shared/ScoreDerivationTree'

// Composite lens weights (atlas_thresholds.lens_weight_*; valuation/policy = 0). Shown as the
// root formula. TODO(thresholds-panel): read these live so the tree tracks FM edits.
const COMPOSITE_FORMULA = '= 0.30·Tech + 0.25·Fund + 0.25·Flow + 0.20·Cat'
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

export function stockToDerivation(symbol: string, name: string | null, ladder: StockLadder): DerivRoot {
  const strength = ladder.strength

  const lenses: DerivNode[] = ladder.lenses.map((l) => {
    const additive = ADDITIVE.has(l.key)
    // sub-component nodes; each pulls its underlying variables (from the lens's actual numbers)
    const subNodes: DerivNode[] = l.subs.map((s) => {
      const m = SUB_MAP[s.label]
      const kids: DerivNode[] = (m?.vars ?? [])
        .flatMap((kw) => l.numbers.filter((nm) => nm.label.includes(kw)))
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
    const leftover = l.numbers.filter((nm) => !mappedLabels.has(nm.label))
    const children: DerivNode[] = [...subNodes]
    if (leftover.length) {
      children.push({
        id: `${l.key}-inputs`, label: 'Underlying inputs',
        children: leftover.map((nm) => ({ id: `${l.key}-in-${nm.label}`, label: nm.label, value: nm.value, tone: nm.tone })),
      })
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

  return {
    title: name ? `${symbol} · ${name}` : symbol,
    headline: { label: 'Conviction', value: strength != null ? `${strength.toFixed(1)}/10` : '—', decile: strength != null ? Math.round(strength) : null },
    formula: COMPOSITE_FORMULA,
    lenses,
  }
}
