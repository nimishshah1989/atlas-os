'use client'
// Desk v2 approval queue — pending trade cards with one-tap approve/reject.
// Renders nothing when the queue is empty (auto desks keep the board quiet).
import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import type { PendingOrder } from '@/lib/queries/desk'
import { Panel } from '@/components/ui/Panel'

export function DeskQueue({ orders }: { orders: PendingOrder[] }) {
  const router = useRouter()
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [, startTransition] = useTransition()
  if (orders.length === 0) return null

  async function decide(id: number, action: 'approve' | 'reject') {
    setBusy(id)
    setError(null)
    const res = await fetch('/api/desk/orders', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ id, action }),
    })
    setBusy(null)
    if (!res.ok) {
      const j = await res.json().catch(() => null)
      setError(j?.message ?? `request failed (${res.status})`)
      return
    }
    startTransition(() => router.refresh())
  }

  return (
    <Panel
      eyebrow="Desk approval queue"
      title={`${orders.length} order${orders.length === 1 ? '' : 's'} awaiting your decision`}
      info={{
        body: 'Trade cards proposed by an approval-mode desk. Approving books the trade through the audited engine at the next nightly settlement; unapproved cards expire automatically.',
      }}
      bodyClassName="px-5 py-4"
    >
      {error && <p className="mb-3 font-sans text-[13px] text-neg">{error}</p>}
      <ul className="space-y-3">
        {orders.map((o) => (
          <li key={o.id} className="rounded-lg border border-edge-hair px-4 py-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span
                className={`font-num text-[11px] uppercase tracking-[0.1em] ${o.side === 'buy' ? 'text-pos' : 'text-neg'}`}
              >
                {o.side}
              </span>
              <span className="font-display text-[15px] font-medium text-txt-1">{o.symbol}</span>
              <span className="font-num text-[12px] text-txt-3">
                {o.portfolio} · {o.cycleDate}
              </span>
              {o.stop !== null && o.target !== null && (
                <span className="font-num text-[12px] text-txt-2">
                  entry {o.entryRef} · stop {o.stop} · target {o.target} · R:R {o.rr}
                </span>
              )}
              <span className="ml-auto flex gap-2">
                <button
                  onClick={() => decide(o.id, 'approve')}
                  disabled={busy === o.id}
                  className="rounded-md border border-edge-hair px-3 py-1 font-num text-[12px] text-pos hover:bg-surface-inset disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => decide(o.id, 'reject')}
                  disabled={busy === o.id}
                  className="rounded-md border border-edge-hair px-3 py-1 font-num text-[12px] text-neg hover:bg-surface-inset disabled:opacity-50"
                >
                  Reject
                </button>
              </span>
            </div>
            <p className="mt-1.5 font-sans text-[13px] text-txt-2">{o.thesis}</p>
            <p className="mt-0.5 font-sans text-[12px] text-txt-3">Invalid if: {o.invalidation}</p>
            {o.planBasis && (
              <p className="mt-0.5 font-num text-[11px] text-txt-3">levels: {o.planBasis}</p>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}
