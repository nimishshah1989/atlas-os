'use client'
// src/components/portfolios/AddToDraft.tsx — the "+" any row can carry. Toggles the instrument in
// the draft basket (src/lib/basketTray.ts); the tray at the foot of the page offers to build it.
// Stops the click at the cell, because most rows are links.
import { toggleDraft, useDraft, type DraftKind } from '@/lib/basketTray'

export function AddToDraft({ kind, symbol }: { kind: DraftKind; symbol: string }) {
  const draft = useDraft()
  const on = draft[kind].includes(symbol)
  return (
    <button
      type="button"
      className={`add-draft${on ? ' on' : ''}`}
      aria-pressed={on}
      aria-label={on ? `Remove ${symbol} from the draft basket` : `Add ${symbol} to the draft basket`}
      title={on ? 'In the draft basket — click to remove' : 'Add to a draft basket'}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        toggleDraft(kind, symbol)
      }}
    >
      {on ? '✓' : '+'}
    </button>
  )
}
