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
import { decileColor } from '@/components/ui/decile'
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
  href?: string                  // optional secondary link (NOT the primary action)
  bar?: number | null            // 0–100: renders a share bar (e.g. a decile band's weight/count share)
  accent?: string                // colour for the bar + a leading dot (e.g. a band's decile colour)
  metrics?: { label: string; value: string; tone?: 'pos' | 'neg' | 'neutral' }[] // aligned columns (e.g. 1d/1w/1m)
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
    // tinted text only — no pale chip fill (FM: less "Excel highlight")
    return <span className="font-num text-[10px] font-semibold tabular-nums" style={{ color: decileColor(n.decile) }}>D{n.decile}</span>
  }
  if (n.score != null) return <span className="font-num text-[11px] tabular-nums text-txt-2">{n.score.toFixed(0)}<span className="text-[8px] text-txt-3">/100</span></span>
  return null
}

function MetricCells({ metrics }: { metrics: NonNullable<DerivNode['metrics']> }) {
  return <>{metrics.map((m) => (
    <span key={m.label} title={m.label} className={`w-[40px] shrink-0 text-right font-num text-[10.5px] tabular-nums ${toneCls(m.tone)}`}>{m.value}</span>
  ))}</>
}

function NodeRow({ n, selected, onSelect }: { n: DerivNode; selected: boolean; onSelect: () => void }) {
  const hasKids = !!n.children?.length
  const labelEl = (
    <span className="flex min-w-0 items-center gap-1">
      {n.accent && <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: n.accent }} />}
      {n.href
        ? <Link href={n.href} onClick={(e) => e.stopPropagation()} className="truncate font-num text-[12px] text-txt-1 hover:text-brand hover:underline">{n.label}</Link>
        : <span className="truncate font-sans text-[12px] text-txt-1">{n.label}</span>}
      {n.term && <TermInfo term={n.term} />}
    </span>
  )
  const right = (
    <span className="flex shrink-0 items-center gap-2">
      {(n.decile != null || n.score != null) && <Chip n={n} />}
      {n.value != null && <span className={`font-num text-[12px] tabular-nums ${toneCls(n.tone)}`}>{n.value}</span>}
      {n.metrics?.length ? <MetricCells metrics={n.metrics} /> : null}
      {n.weightPct != null && <span className="w-[34px] shrink-0 text-right font-num text-[9px] tabular-nums text-txt-3">{n.weightPct.toFixed(n.weightPct < 10 ? 1 : 0)}%</span>}
      {hasKids && <span className="font-num text-[11px] text-txt-3">›</span>}
    </span>
  )
  const cls = `flex w-full items-center justify-between gap-2 rounded-tile border px-2.5 py-1.5 text-left transition-colors ${selected ? 'border-brand bg-surface-raised' : 'border-edge-hair bg-surface-panel'} ${hasKids ? 'hover:bg-surface-raised/60' : ''}`
  // share bar (n.bar, e.g. decile-band weight share) takes priority; falls back to the score bar.
  const barPct = n.bar != null ? n.bar : n.contribution != null && n.score != null ? n.score : null
  const barColor = n.accent ?? (n.score != null ? scoreColor(n.score) : 'var(--color-brand)')
  const bar = barPct != null ? (
    <span className="mt-0.5 block h-[3px] w-full overflow-hidden rounded-full bg-surface-inset">
      <span className="block h-full rounded-full" style={{ width: `${Math.min(100, Math.max(2, barPct))}%`, background: barColor }} />
    </span>
  ) : null

  // nodes with children drill (role=button div — NOT a <button>, since the label may itself be a
  // secondary <a> link, e.g. a constituent that both drills inline AND links to its stock page;
  // a nested <a> in <button> is invalid HTML). leaves (variables) display in place.
  if (hasKids)
    return (
      <div>
        <div
          role="button"
          tabIndex={0}
          onClick={onSelect}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}
          className={`${cls} cursor-pointer`}
          aria-expanded={selected}
        >
          {labelEl}{right}
        </div>
        {bar}
      </div>
    )
  return <div><div className={`${cls} cursor-default`}>{labelEl}{right}</div>{bar}</div>
}

function Column({ nodes, parentFormula, selectedId, onSelect }: { nodes: DerivNode[]; parentFormula?: string; selectedId?: string; onSelect: (id: string) => void }) {
  const metricLabels = nodes.find((x) => x.metrics?.length)?.metrics?.map((m) => m.label)
  return (
    <div className="flex w-[300px] shrink-0 flex-col gap-1.5 border-l border-edge-rule pl-3">
      {parentFormula && <p className="px-0.5 font-num text-[9px] leading-snug text-txt-3">{parentFormula}</p>}
      {metricLabels && (
        <div className="flex items-center justify-end gap-2 pr-7 font-num text-[8px] uppercase tracking-wider text-txt-3">
          {metricLabels.map((l) => <span key={l} className="w-[40px] text-right">{l}</span>)}
        </div>
      )}
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
