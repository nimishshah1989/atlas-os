// src/components/entity/FactList.tsx — the one fact list: label, value, and where the value came
// from (source and as-of). Hairlines between rows, no card. Every fact on a detail page names its
// source in the third column; a fact without one is a derivation of the facts above it.
import type { ReactNode } from 'react'

export type Fact = { label: string; value: ReactNode; source?: ReactNode }

export function FactList({ facts, className = '' }: { facts: Fact[]; className?: string }) {
  return (
    <dl className={`facts ${className}`}>
      {facts.map((f) => (
        <div key={f.label} className="fact">
          <dt className="text-meta text-ink-3">{f.label}</dt>
          <dd className="text-body text-ink">{f.value}</dd>
          <dd className="fact-src text-meta text-ink-3">{f.source}</dd>
        </div>
      ))}
    </dl>
  )
}
