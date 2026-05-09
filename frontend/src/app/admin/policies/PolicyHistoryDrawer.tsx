'use client'

import { useEffect, useState } from 'react'
import { getPolicyHistoryAction } from './actions'
import type { PolicyHistoryRow } from '@/lib/queries/policies'
import { formatIST } from '@/lib/format-date'

type Props = {
  policyKey: string
  onClose: () => void
}

function formatPolicyValue(val: string[] | Record<string, string> | null): string {
  if (val === null || val === undefined) return '—'
  if (Array.isArray(val)) return val.length === 0 ? '(empty)' : val.join(', ')
  return Object.entries(val).map(([k, v]) => `${k}=${v}`).join(', ')
}

export function PolicyHistoryDrawer({ policyKey, onClose }: Props) {
  const [rows, setRows] = useState<PolicyHistoryRow[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFetchError(null)
    getPolicyHistoryAction(policyKey)
      .then((data) => {
        if (!cancelled) {
          setRows(data)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : String(err))
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [policyKey])

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-ink-primary/20" onClick={onClose} />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="false"
        aria-labelledby="policy-history-drawer-title"
        className="fixed top-0 right-0 z-50 h-full w-[520px] max-w-full bg-paper border-l border-paper-rule shadow-lg flex flex-col"
      >
        {/* Header */}
        <div className="border-b border-paper-rule px-6 py-4 flex items-start justify-between flex-shrink-0">
          <div>
            <h2 id="policy-history-drawer-title" className="font-serif text-lg text-ink-primary">Policy History</h2>
            <p className="font-mono text-xs text-ink-tertiary mt-0.5">{policyKey}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="font-sans text-ink-tertiary hover:text-ink-primary transition-colors text-xl leading-none mt-0.5"
            aria-label="Close history drawer"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading && (
            <p className="font-sans text-xs text-ink-tertiary">Loading history…</p>
          )}

          {fetchError && (
            <p className="font-sans text-xs text-signal-neg">{fetchError}</p>
          )}

          {!loading && !fetchError && rows !== null && rows.length === 0 && (
            <p className="font-sans text-xs text-ink-tertiary">No edits yet.</p>
          )}

          {!loading && !fetchError && rows !== null && rows.length > 0 && (
            <div className="flex flex-col gap-4">
              {rows.map((row) => (
                <div key={row.id} className="border border-paper-rule rounded-[2px] p-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-sans text-xs text-ink-tertiary whitespace-nowrap">
                      {formatIST(row.changed_at, true)}
                    </span>
                    <span className="font-sans text-xs text-ink-secondary">{row.changed_by}</span>
                  </div>
                  <div className="flex flex-col gap-1 mb-1.5">
                    <p className="font-sans text-xs text-ink-tertiary">From:</p>
                    <p className="font-mono text-xs text-signal-neg break-all">
                      {formatPolicyValue(row.old_value as string[] | Record<string, string> | null)}
                    </p>
                    <p className="font-sans text-xs text-ink-tertiary">To:</p>
                    <p className="font-mono text-xs text-signal-pos break-all">
                      {formatPolicyValue(row.new_value as string[] | Record<string, string>)}
                    </p>
                  </div>
                  {row.change_reason && (
                    <p className="font-sans text-xs text-ink-secondary italic leading-relaxed">
                      "{row.change_reason}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
