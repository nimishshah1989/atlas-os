// src/components/entity/FactList.tsx — the one fact list: label, value, and where the value came
// from (source and as-of). Hairlines between rows, no card. Every fact on a detail page names its
// source in the third column; a fact without one is a derivation of the facts above it.
//
// THE SOURCE COLUMN IS ONE LINE, NEVER TWO. Provenance is a fact and is never dropped, but a
// 45-character source repeated down a column was reading as a second body of text beside the
// values. It is truncated to the column and carries the whole string on hover — India's move
// (InfoTip / TermInfo): the fact stays, the words go. A source shared by EVERY row of a list
// belongs in the section's note instead, said once.
import type { ReactNode } from 'react'

export type Fact = { label: string; value: ReactNode; source?: ReactNode }

/** A `title` needs a string; a source given as a node keeps its markup and loses the hover. */
const hover = (source: ReactNode) => (typeof source === 'string' ? source : undefined)

export function FactList({ facts, className = '' }: { facts: Fact[]; className?: string }) {
  return (
    <dl className={`facts ${className}`}>
      {facts.map((f) => (
        <div key={f.label} className="fact">
          <dt className="text-meta text-ink-3">{f.label}</dt>
          <dd className="text-body text-ink">{f.value}</dd>
          <dd className="fact-src truncate text-meta text-ink-3" title={hover(f.source)}>
            {f.source}
          </dd>
        </div>
      ))}
    </dl>
  )
}
