// src/components/entity/EntityHeader.tsx — the one entity header: the name in serif, the symbol
// line beneath it, and the facts with their sources. No card, no score yet (the Lens bar joins
// once the instrument is scored).
import type { ReactNode } from 'react'
import { FactList, type Fact } from './FactList'

export function EntityHeader({ name, line, facts }: { name: string; line: ReactNode; facts: Fact[] }) {
  return (
    <header className="entity">
      <h1 className="font-serif text-title text-ink">{name}</h1>
      <p className="mt-2 text-lead text-ink-2">{line}</p>
      <FactList facts={facts} className="mt-6" />
    </header>
  )
}
