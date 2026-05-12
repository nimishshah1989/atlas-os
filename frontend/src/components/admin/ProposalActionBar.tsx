'use client'
// SP04 Stage 4a — client-side approve/reject/snooze for one proposal.
// On success, refresh the page so the proposal disappears from "pending"
// list. On failure, surface the error text inline.
import { useState } from 'react'
import { useRouter } from 'next/navigation'

type Action = 'approve' | 'reject' | 'snooze'

type Props = {
  proposalId: string
  apiBase?: string // defaults to '' (same-origin); useful for testing
}

export function ProposalActionBar({ proposalId, apiBase = '' }: Props) {
  const router = useRouter()
  const [busy, setBusy] = useState<Action | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [snoozeUntil, setSnoozeUntil] = useState('')

  async function dispatch(action: Action) {
    setBusy(action)
    setError(null)
    const body: Record<string, unknown> = { notes: notes || undefined }
    if (action === 'snooze') {
      if (!snoozeUntil) {
        setError('Pick a snooze-until date first.')
        setBusy(null)
        return
      }
      body.until_date = snoozeUntil
    }
    try {
      const resp = await fetch(
        `${apiBase}/api/admin/proposals/${proposalId}/${action}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
      )
      if (!resp.ok) {
        const txt = await resp.text()
        throw new Error(`HTTP ${resp.status}: ${txt.slice(0, 200)}`)
      }
      router.refresh()
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-2 mt-3">
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={2}
        placeholder="Reviewer notes (optional)"
        className="w-full border border-paper-rule rounded-sm px-2 py-1 font-sans text-xs text-ink-primary bg-white"
      />
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => dispatch('approve')}
          disabled={busy !== null}
          className="px-3 py-1.5 font-sans text-xs font-semibold rounded-sm bg-teal text-white hover:opacity-90 disabled:opacity-50"
        >
          {busy === 'approve' ? 'Applying…' : 'Approve (15% blend)'}
        </button>
        <button
          onClick={() => dispatch('reject')}
          disabled={busy !== null}
          className="px-3 py-1.5 font-sans text-xs font-semibold rounded-sm border border-paper-rule text-ink-primary hover:bg-paper-rule/30 disabled:opacity-50"
        >
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </button>
        <input
          type="date"
          value={snoozeUntil}
          onChange={(e) => setSnoozeUntil(e.target.value)}
          className="px-2 py-1 border border-paper-rule rounded-sm font-sans text-xs text-ink-primary bg-white"
        />
        <button
          onClick={() => dispatch('snooze')}
          disabled={busy !== null}
          className="px-3 py-1.5 font-sans text-xs font-semibold rounded-sm border border-paper-rule text-ink-secondary hover:bg-paper-rule/30 disabled:opacity-50"
        >
          {busy === 'snooze' ? 'Snoozing…' : 'Snooze until…'}
        </button>
      </div>
      {error && (
        <p className="font-sans text-[11px] text-signal-neg mt-1">{error}</p>
      )}
    </div>
  )
}
