// src/components/ui/PageHeader.tsx — the page head (h1 1.3rem/600) and an optional lead sentence
// at the prose measure.
import type { ReactNode } from 'react'

export function PageHeader({ title, lead, aside }: { title: string; lead?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-serif text-title text-ink">{title}</h1>
        {lead && <p className="mt-1.5 max-w-(--measure) text-lead text-ink-2">{lead}</p>}
      </div>
      {aside}
    </header>
  )
}
