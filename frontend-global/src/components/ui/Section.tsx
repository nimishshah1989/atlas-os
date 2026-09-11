// src/components/ui/Section.tsx — a titled block (h2 1.05rem/600) with an optional note beside it.
import Link from 'next/link'
import type { ReactNode } from 'react'

export function Section({
  title,
  href,
  note,
  aside,
  children,
}: {
  title: string
  /** Where the title goes when the section is a summary of a board — the whole population. */
  href?: string
  note?: ReactNode
  /** A control that belongs to this section — a range picker, a toggle. It sits on the title row
   *  rather than above the content, so a section's own switch is never mistaken for the page's. */
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="mt-8">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-serif text-h2 text-ink">
          {href ? (
            <Link href={href} className="hover:underline" title="Open the whole board">
              {title} →
            </Link>
          ) : (
            title
          )}
        </h2>
        <span className="flex flex-wrap items-center gap-3">
          {note && <span className="text-meta text-ink-3">{note}</span>}
          {aside}
        </span>
      </div>
      {children}
    </section>
  )
}

/** What a table shows when a query failed: what failed, and what to do. */
export function QueryFailed({ error }: { error: string }) {
  return (
    <p className="panel px-4 py-3 text-body text-ink-2">
      The database did not answer this query. Check the pooler URL and the atlas_global_app grants, then
      reload. It said: <span className="text-neg">{error}</span>
    </p>
  )
}
