'use client'

import { useEffect, useRef, useState } from 'react'
import { triggerRecompute, getRunStatusAction } from './actions'
import type { RecentRunRow } from '@/lib/queries/thresholds'
import { formatIST } from '@/lib/format-date'

type Milestone = 'm3' | 'm4' | 'm5' | 'all'

type Props = {
  recentRuns: RecentRunRow[]
}

type RunStatus = 'running' | 'success' | 'failed'

const STATUS_CLASSES: Record<RunStatus, string> = {
  running: 'text-signal-warn bg-signal-warn/10 border-signal-warn/20',
  success: 'text-signal-pos bg-signal-pos/10 border-signal-pos/20',
  failed: 'text-signal-neg bg-signal-neg/10 border-signal-neg/20',
}

function statusClass(status: string): string {
  return STATUS_CLASSES[status as RunStatus] ?? 'text-ink-secondary bg-paper-rule/20 border-paper-rule'
}

export function RecomputePanel({ recentRuns: initialRuns }: Props) {
  const [runs, setRuns] = useState<RecentRunRow[]>(initialRuns)
  const [activeMilestone, setActiveMilestone] = useState<Milestone | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [messageKind, setMessageKind] = useState<'ok' | 'err'>('ok')
  const [pollingRunId, setPollingRunId] = useState<string | null>(null)

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Stop polling when component unmounts
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  function stopPolling() {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  function startPolling(runId: string) {
    stopPolling()
    setPollingRunId(runId)
    pollingRef.current = setInterval(async () => {
      const row = await getRunStatusAction(runId)
      if (!row) return
      // Update the run in our local list
      setRuns((prev) => {
        const exists = prev.some((r) => r.run_id === runId)
        if (exists) return prev.map((r) => (r.run_id === runId ? row : r))
        return [row, ...prev].slice(0, 5)
      })
      if (row.status === 'success' || row.status === 'failed') {
        stopPolling()
        setPollingRunId(null)
        const label = row.status === 'success' ? 'completed successfully' : 'failed'
        setMessage(`Run ${runId.slice(0, 8)}… ${label}`)
        setMessageKind(row.status === 'success' ? 'ok' : 'err')
        setActiveMilestone(null)
      }
    }, 5000)
  }

  async function handleTrigger(milestone: Milestone) {
    setActiveMilestone(milestone)
    setMessage(null)
    const result = await triggerRecompute(milestone)
    if (result.ok) {
      setMessage(`Recompute started, run_id=${result.compute_run_id}`)
      setMessageKind('ok')
      startPolling(result.compute_run_id)
    } else {
      const suffix = result.existing_run_id
        ? ` (run_id=${result.existing_run_id.slice(0, 8)}…)`
        : ''
      setMessage(result.error + suffix)
      setMessageKind('err')
      setActiveMilestone(null)
    }
  }

  function handleRefresh() {
    window.location.reload()
  }

  const BUTTONS: { label: string; milestone: Milestone }[] = [
    { label: 'M3', milestone: 'm3' },
    { label: 'M4', milestone: 'm4' },
    { label: 'M5', milestone: 'm5' },
    { label: 'All', milestone: 'all' },
  ]

  return (
    <div className="border border-paper-rule rounded-[2px] mb-6 bg-paper">
      {/* Panel header */}
      <div className="border-b border-paper-rule px-4 py-3 flex items-center justify-between">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Recompute Pipeline
        </h2>
        <button
          type="button"
          onClick={handleRefresh}
          className="font-sans text-xs text-ink-secondary hover:text-ink-primary transition-colors"
        >
          Refresh status
        </button>
      </div>

      {/* Trigger buttons */}
      <div className="px-4 py-4 flex flex-wrap items-center gap-3">
        {BUTTONS.map(({ label, milestone }) => (
          <button
            key={milestone}
            type="button"
            onClick={() => handleTrigger(milestone)}
            disabled={activeMilestone !== null}
            className="bg-accent text-paper font-sans text-sm px-4 py-1.5 rounded-[2px] hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {activeMilestone === milestone ? 'Triggering…' : `Re-run ${label}`}
          </button>
        ))}
        {pollingRunId && (
          <span className="font-sans text-xs text-ink-tertiary animate-pulse">
            Polling run {pollingRunId.slice(0, 8)}…
          </span>
        )}
      </div>

      {/* Inline message */}
      {message && (
        <div className={`mx-4 mb-4 px-3 py-2 rounded-[2px] border font-sans text-xs ${messageKind === 'ok'
          ? 'text-signal-pos bg-signal-pos/10 border-signal-pos/20'
          : 'text-signal-neg bg-signal-neg/10 border-signal-neg/20'
        }`}>
          {message}
        </div>
      )}

      {/* Recent runs */}
      {runs.length > 0 && (
        <div className="border-t border-paper-rule px-4 py-3">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-2">
            Recent runs
          </p>
          <div className="flex flex-col gap-1.5">
            {runs.map((run) => (
              <div key={run.run_id} className="flex items-center gap-3 flex-wrap">
                <span className={`font-sans text-xs border rounded-[2px] px-1.5 py-0.5 ${statusClass(run.status)}`}>
                  {run.status}
                </span>
                <span className="font-mono text-xs text-ink-tertiary">
                  {run.run_id.slice(0, 12)}…
                </span>
                {run.milestone && (
                  <span className="font-sans text-xs text-ink-secondary">
                    {run.milestone.toUpperCase()}
                  </span>
                )}
                <span className="font-sans text-xs text-ink-secondary">{run.script_name}</span>
                <span className="font-sans text-xs text-ink-tertiary">
                  {formatIST(run.started_at, true)}
                </span>
                {run.rows_written && (
                  <span className="font-sans text-xs text-ink-tertiary">
                    {run.rows_written} rows
                  </span>
                )}
                {run.error_message && (
                  <span className="font-sans text-xs text-signal-neg truncate max-w-xs" title={run.error_message}>
                    {run.error_message}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
