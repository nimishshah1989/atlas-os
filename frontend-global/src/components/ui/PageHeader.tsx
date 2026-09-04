// src/components/ui/PageHeader.tsx — serif page title (32/36) and an optional lead sentence.
import type { ReactNode } from 'react'

export function PageHeader({ title, lead, aside }: { title: string; lead?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-serif text-title text-ink">{title}</h1>
        {lead && <p className="mt-2 max-w-[64ch] text-lead text-ink-2">{lead}</p>}
      </div>
      {aside}
    </header>
  )
}
