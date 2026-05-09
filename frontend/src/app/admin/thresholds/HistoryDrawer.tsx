'use client'

import { useEffect, useState } from 'react'
import { getThresholdHistoryAction } from './actions'
import type { ThresholdHistoryRow } from '@/lib/queries/thresholds'
import { formatIST } from '@/lib/format-date'

type Props = {
  thresholdKey: string
  onClose: () => void
}

export function HistoryDrawer({ thresholdKey, onClose }: Props) {
  const [rows, setRows] = useState<ThresholdHistoryRow[] | null>(null)
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
    getThresholdHistoryAction(thresholdKey)
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
  }, [thresholdKey])

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-ink-primary/20"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="false"
        aria-labelledby="history-drawer-title"
        className="fixed top-0 right-0 z-50 h-full w-[480px] max-w-full bg-paper border-l border-paper-rule shadow-lg flex flex-col"
      >
        {/* Header */}
        <div className="border-b border-paper-rule px-6 py-4 flex items-start justify-between flex-shrink-0">
          <div>
            <h2 id="history-drawer-title" className="font-serif text-lg text-ink-primary">Threshold History</h2>
            <p className="font-mono text-xs text-ink-tertiary mt-0.5">{thresholdKey}</p>
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
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-paper-rule">
                  <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-3">
                    When
                  </th>
                  <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-3">
                    Change
                  </th>
                  <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-3">
                    By
                  </th>
                  <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2">
                    Reason
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-paper-rule/40 hover:bg-paper-rule/10">
                    <td className="py-2.5 pr-3 align-top">
                      <span className="font-sans text-xs text-ink-secondary whitespace-nowrap">
                        {formatIST(row.changed_at, true)}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 align-top">
                      <span className="font-mono text-xs text-signal-neg">
                        {row.old_value ?? '—'}
                      </span>
                      <span className="font-sans text-xs text-ink-tertiary mx-1">→</span>
                      <span className="font-mono text-xs text-signal-pos">
                        {row.new_value}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 align-top">
                      <span className="font-sans text-xs text-ink-secondary">{row.changed_by}</span>
                    </td>
                    <td className="py-2.5 align-top">
                      <span className="font-sans text-xs text-ink-secondary leading-relaxed">
                        {row.change_reason ?? <span className="text-ink-tertiary italic">—</span>}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
