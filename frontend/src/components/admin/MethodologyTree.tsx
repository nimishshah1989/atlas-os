'use client'
// MethodologyTree — the whole Atlas methodology as a click-to-expand tree, in plain terms.
// Structural nodes (the score, the lenses, the roll-ups) carry an authored plain-English line +
// the actual calculation; leaf metrics pull their definition from the SAME glossary the column
// info-icons use, so the explanation is identical everywhere. Nothing here is instrument-specific.
import { useState } from 'react'
import { GLOSSARY } from '@/lib/glossary'

export type MethoNode = {
  id: string
  title: string
  plain?: string        // layman one-liner (authored)
  formula?: string      // the actual calculation / derivation
  weight?: string       // optional weight chip (e.g. "0.30")
  term?: string         // pull title+plain from the glossary (leaf metrics) — keeps wording consistent
  children?: MethoNode[]
}

function Node({ n, depth }: { n: MethoNode; depth: number }) {
  const g = n.term ? GLOSSARY[n.term] : undefined
  const title = n.title || g?.title || n.term || ''
  const plain = n.plain ?? g?.body
  const hasKids = !!n.children?.length
  const [open, setOpen] = useState(depth === 0)

  return (
    <div className={depth > 0 ? 'border-l border-edge-hair/70 pl-3' : ''}>
      <button
        type="button"
        onClick={() => hasKids && setOpen((v) => !v)}
        aria-expanded={hasKids ? open : undefined}
        className={`flex w-full items-start gap-2 rounded-tile px-2 py-1.5 text-left transition-colors ${hasKids ? 'hover:bg-surface-raised' : 'cursor-default'}`}
      >
        <span className="mt-[3px] w-3 shrink-0 font-num text-[10px] text-txt-3">{hasKids ? (open ? '▾' : '▸') : '·'}</span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-baseline gap-2">
            <span className={`font-sans ${depth === 0 ? 'text-[15px] font-semibold' : 'text-[13px] font-medium'} text-txt-1`}>{title}</span>
            {n.weight && <span className="rounded px-1.5 py-0.5 font-num text-[10px] tabular-nums text-brand" style={{ background: 'color-mix(in srgb, var(--color-brand) 12%, transparent)' }}>weight {n.weight}</span>}
          </span>
          {plain && <span className="mt-0.5 block font-sans text-[12px] leading-[1.5] text-txt-2">{plain}</span>}
          {n.formula && <span className="mt-1 block rounded-tile bg-surface-inset px-2 py-1 font-num text-[11px] leading-[1.45] text-txt-2">{n.formula}</span>}
        </span>
      </button>
      {hasKids && open && (
        <div className="ml-3 mt-0.5 space-y-0.5">
          {n.children!.map((c) => <Node key={c.id} n={c} depth={depth + 1} />)}
        </div>
      )}
    </div>
  )
}

export function MethodologyTree({ roots }: { roots: MethoNode[] }) {
  return (
    <div className="space-y-2">
      {roots.map((r) => (
        <div key={r.id} className="rounded-panel border border-edge-hair bg-surface-panel p-2">
          <Node n={r} depth={0} />
        </div>
      ))}
    </div>
  )
}
