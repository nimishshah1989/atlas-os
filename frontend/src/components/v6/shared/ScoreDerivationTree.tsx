'use client'
// ScoreDerivationTree — the canonical "how the score is built" view, reused across
// stock / sector / ETF / fund. Horizontal Miller-column drill (Variant B): pick a node and
// its children open in the next column to the right. Leaves show the real value + an eye-icon
// explainer. For aggregates, a lens expands into its constituents/holdings (by contribution);
// each constituent links to its own page (where its full tree lives).
//
// Data is supplied by thin per-entity adapters (stockToDerivation, sectorToDerivation, …) so
// this component stays presentation-only. Weights/formulas come from atlas_thresholds upstream,
// so it stays consistent with the (upcoming) editable Thresholds panel.
import { useState } from 'react'
import Link from 'next/link'
import { decileColor } from '@/components/v4/ui/decile'
import { TermInfo } from './TermInfo'

export type DerivNode = {
  id: string
  label: string
  decile?: number | null
  score?: number | null          // 0–100 (lens / sub-score) or the headline figure
  weightPct?: number | null      // this node's share of its parent
  contribution?: number | null   // weight × score (what it actually adds)
  value?: string | null          // leaf: the real variable value
  tone?: 'pos' | 'neg' | 'neutral'
  term?: string                  // glossary key → eye-icon explainer
  formula?: string               // roll-up shown atop this node's child column
  href?: string                  // constituent → its own page
  children?: DerivNode[]
}
export type DerivRoot = {
  title: string                  // entity name
  headline: { label: string; value: string; decile?: number | null }
  formula?: string               // composite formula (e.g. 0.30·Tech + …)
  lenses: DerivNode[]            // top-level children (the lenses)
}

const toneCls = (t?: DerivNode['tone']) => (t === 'pos' ? 'text-sig-pos' : t === 'neg' ? 'text-sig-neg' : 'text-txt-1')
const scoreColor = (v: number) => (v >= 60 ? 'var(--color-sig-pos)' : v >= 45 ? 'var(--color-sig-warn)' : 'var(--color-sig-neg)')

function Chip({ n }: { n: DerivNode }) {
  if (n.decile != null) {
    const c = decileColor(n.decile)
    return <span className="rounded px-1.5 py-0.5 font-num text-[10px] font-semibold tabular-nums" style={{ background: `color-mix(in srgb, ${c} 20%, transparent)`, color: c }}>D{n.decile}</span>
  }
  if (n.score != null) return <span className="font-num text-[11px] tabular-nums text-txt-2">{n.score.toFixed(0)}<span className="text-[8px] text-txt-3">/100</span></span>
  return null
}

function NodeRow({ n, selected, onSelect }: { n: DerivNode; selected: boolean; onSelect: () => void }) {
  const hasKids = !!n.children?.length
  const inner = (
    <>
      <span className="flex min-w-0 items-center gap-1">
        <span className="truncate font-sans text-[12px] text-txt-1">{n.label}</span>
        {n.term && <TermInfo term={n.term} />}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {n.value != null
          ? <span className={`font-num text-[12px] tabular-nums ${toneCls(n.tone)}`}>{n.value}</span>
          : <Chip n={n} />}
        {n.weightPct != null && <span className="font-num text-[9px] tabular-nums text-txt-3">{(n.weightPct).toFixed(n.weightPct < 10 ? 1 : 0)}%</span>}
        {(hasKids || n.href) && <span className="font-num text-[11px] text-txt-3">›</span>}
      </span>
    </>
  )
  const cls = `flex w-full items-center justify-between gap-2 rounded-tile border px-2.5 py-1.5 text-left transition-colors ${selected ? 'border-brand bg-surface-raised' : 'border-edge-hair bg-surface-panel hover:bg-surface-raised/60'}`
  // contribution bar under the row (when it's a weighted contributor)
  const bar = n.contribution != null && n.score != null ? (
    <span className="mt-0.5 block h-[3px] w-full overflow-hidden rounded-full bg-surface-inset">
      <span className="block h-full rounded-full" style={{ width: `${Math.min(100, n.score)}%`, background: scoreColor(n.score) }} />
    </span>
  ) : null

  if (!hasKids && n.href) {
    return <div><Link href={n.href} className={cls}>{inner}</Link>{bar}</div>
  }
  return <div><button type="button" onClick={onSelect} className={cls} aria-expanded={selected}>{inner}</button>{bar}</div>
}

function Column({ nodes, parentFormula, selectedId, onSelect }: { nodes: DerivNode[]; parentFormula?: string; selectedId?: string; onSelect: (id: string) => void }) {
  return (
    <div className="flex w-[260px] shrink-0 flex-col gap-1.5 border-l border-edge-rule pl-3">
      {parentFormula && <p className="px-0.5 font-num text-[9px] leading-snug text-txt-3">{parentFormula}</p>}
      {nodes.map((n) => <NodeRow key={n.id} n={n} selected={n.id === selectedId} onSelect={() => onSelect(n.id)} />)}
    </div>
  )
}

export function ScoreDerivationTree({ root }: { root: DerivRoot }) {
  // path[i] = selected node id at column i (column 0 = lenses).
  const [path, setPath] = useState<string[]>([])

  // Resolve the columns from the path.
  const columns: { nodes: DerivNode[]; parentFormula?: string }[] = [{ nodes: root.lenses }]
  let level = root.lenses
  for (let i = 0; i < path.length; i++) {
    const sel = level.find((n) => n.id === path[i])
    if (!sel?.children?.length) break
    columns.push({ nodes: sel.children, parentFormula: sel.formula })
    level = sel.children
  }
  const select = (col: number, id: string) => setPath((p) => [...p.slice(0, col), id])

  const h = root.headline
  return (
    <div className="flex items-start gap-3 overflow-x-auto pb-3">
      {/* root headline (left) */}
      <div className="shrink-0 rounded-tile border border-edge-rule bg-surface-raised px-4 py-3 text-center shadow-panel">
        <div className="font-num text-[9px] uppercase tracking-[0.16em] text-txt-3">{h.label}</div>
        <div className="font-display text-[26px] font-semibold leading-none tabular-nums" style={{ color: h.decile != null ? decileColor(h.decile) : 'var(--color-txt-1)' }}>{h.value}</div>
        {root.formula && <div className="mt-1.5 max-w-[150px] font-num text-[8.5px] leading-snug text-txt-3">{root.formula}</div>}
      </div>
      {columns.map((c, i) => (
        <Column key={i} nodes={c.nodes} parentFormula={c.parentFormula} selectedId={path[i]} onSelect={(id) => select(i, id)} />
      ))}
    </div>
  )
}
