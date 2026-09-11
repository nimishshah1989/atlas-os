'use client'
// src/components/portfolios/DraftTray.tsx — the draft basket, at the foot of every page while it
// holds anything. One line per kind: the names, a way to build, a way to clear. Building opens the
// builder seeded with the names (equal-weighted, a starting point) and empties the draft, because
// from that moment the form is the draft.
import Link from 'next/link'
import { clearDraft, draftHref, useDraft, type DraftKind } from '@/lib/basketTray'

const NOUN: Record<DraftKind, string> = { etf: 'ETF', stock: 'stock' }

export function DraftTray() {
  const draft = useDraft()
  const kinds = (['etf', 'stock'] as const).filter((k) => draft[k].length > 0)
  if (kinds.length === 0) return null
  return (
    <aside className="draft-tray panel" aria-label="Draft basket" data-testid="draft-tray">
      {kinds.map((k) => (
        <div key={k} className="draft-row">
          <span className="text-meta text-ink-3">
            Draft {NOUN[k]} basket · <span className="num text-ink">{draft[k].length}</span>
          </span>
          <span className="draft-names num text-table text-ink" title={draft[k].join(', ')}>
            {draft[k].join(' · ')}
          </span>
          <Link href={draftHref(k, draft)} className="btn btn-primary text-meta" onClick={() => clearDraft(k)}>
            Build basket →
          </Link>
          <button type="button" className="btn btn-quiet text-meta" onClick={() => clearDraft(k)}>
            Clear
          </button>
        </div>
      ))}
    </aside>
  )
}
