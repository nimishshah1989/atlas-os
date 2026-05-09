'use client'

import { useEffect, useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { rerunBacktest, getBacktestRunStatus } from '@/app/strategies/[id]/actions'

type Props = {
  strategyId: string
  strategyName: string
  onClose: () => void
}

function defaultStartDate(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 5)
  return d.toISOString().slice(0, 10)
}

function defaultEndDate(): string {
  return new Date().toISOString().slice(0, 10)
}

export function ReRunBacktestModal({ strategyId, strategyName, onClose }: Props) {
  const router = useRouter()

  const [startDate, setStartDate] = useState<string>(() => defaultStartDate())
  const [endDate, setEndDate] = useState<string>(() => defaultEndDate())
  const [capital, setCapital] = useState<number>(1_000_000)

  const [startErr, setStartErr] = useState<string | null>(null)
  const [endErr, setEndErr] = useState<string | null>(null)
  const [capitalErr, setCapitalErr] = useState<string | null>(null)
  const [topError, setTopError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const [pollingRunId, setPollingRunId] = useState<string | null>(null)
  const [elapsedSec, setElapsedSec] = useState(0)
  const [isPending, startTransition] = useTransition()

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ESC to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopPolling()
    }
  }, [])

  function stopPolling() {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
    if (elapsedRef.current) { clearInterval(elapsedRef.current); elapsedRef.current = null }
  }

  function handleClose() {
    stopPolling()
    onClose()
  }

  function startPolling(runId: string) {
    stopPolling()
    setPollingRunId(runId)
    setElapsedSec(0)

    // Elapsed timer — ticks every second
    elapsedRef.current = setInterval(() => {
      setElapsedSec((s) => s + 1)
    }, 1000)

    // Status poll — every 5 seconds
    pollingRef.current = setInterval(async () => {
      const row = await getBacktestRunStatus(runId)
      if (!row) return
      if (row.status === 'success' || row.status === 'failed') {
        stopPolling()
        setPollingRunId(null)
        if (row.status === 'success') {
          setSuccessMsg('Backtest completed successfully. Refreshing results…')
          router.refresh()
        } else {
          setTopError('Backtest failed. Check pipeline logs for details.')
        }
      }
    }, 5000)
  }

  function validate(): boolean {
    let valid = true
    setStartErr(null); setEndErr(null); setCapitalErr(null); setTopError(null)

    if (!startDate) { setStartErr('Start date is required'); valid = false }
    if (!endDate) { setEndErr('End date is required'); valid = false }
    if (startDate && endDate && endDate <= startDate) {
      setEndErr('End date must be after start date'); valid = false
    }
    if (!Number.isFinite(capital) || capital < 100_000) {
      setCapitalErr('Capital must be ≥ ₹1,00,000'); valid = false
    }
    return valid
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return

    startTransition(async () => {
      const result = await rerunBacktest(strategyId, startDate, endDate, capital)
      if (result.ok) {
        setSuccessMsg(`Backtest started — run_id=${result.compute_run_id}`)
        startPolling(result.compute_run_id)
      } else if (result.error_code === 'already_running') {
        const suffix = result.existing_run_id
          ? ` (run_id=${result.existing_run_id.slice(0, 8)}…)`
          : ''
        setTopError(`A backtest for this strategy is already running${suffix}`)
      } else {
        setTopError(result.error)
      }
    })
  }

  const isRunning = pollingRunId !== null
  const submitDisabled = isPending || isRunning

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-primary/20"
      onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rerun-backtest-title"
        className="bg-paper border border-paper-rule rounded-[2px] w-full max-w-md mx-4 shadow-lg"
      >
        {/* Header */}
        <div className="border-b border-paper-rule px-6 py-4 flex items-start justify-between">
          <div>
            <h2 id="rerun-backtest-title" className="font-serif text-lg text-ink-primary leading-tight">
              Re-run Backtest
            </h2>
            <p className="font-sans text-xs text-ink-tertiary mt-0.5 truncate max-w-xs" title={strategyName}>
              {strategyName}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close"
            className="font-sans text-ink-tertiary hover:text-ink-primary text-lg ml-4"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 flex flex-col gap-4">
          {/* Top-level error or success */}
          {topError && (
            <div className="px-3 py-2 rounded-[2px] border text-signal-neg bg-signal-neg/10 border-signal-neg/20 font-sans text-xs">
              {topError}
            </div>
          )}
          {successMsg && (
            <div className="px-3 py-2 rounded-[2px] border text-signal-pos bg-signal-pos/10 border-signal-pos/20 font-sans text-xs">
              {successMsg}
            </div>
          )}

          {/* Polling progress */}
          {isRunning && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-[2px] border border-signal-warn/20 bg-signal-warn/10">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-warn animate-pulse" />
              <span className="font-sans text-xs text-signal-warn">
                Backtest running… ({elapsedSec}s elapsed)
              </span>
            </div>
          )}

          {/* Start date */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="rerun-start-date" className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              Start Date
            </label>
            <input
              id="rerun-start-date"
              type="date"
              value={startDate}
              onChange={(e) => { setStartDate(e.target.value); setStartErr(null) }}
              disabled={submitDisabled}
              className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-mono bg-paper text-ink-primary focus:outline-none focus:border-accent disabled:opacity-60"
            />
            {startErr && <p className="font-sans text-xs text-signal-neg">{startErr}</p>}
          </div>

          {/* End date */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="rerun-end-date" className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              End Date
            </label>
            <input
              id="rerun-end-date"
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); setEndErr(null) }}
              disabled={submitDisabled}
              className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-mono bg-paper text-ink-primary focus:outline-none focus:border-accent disabled:opacity-60"
            />
            {endErr && <p className="font-sans text-xs text-signal-neg">{endErr}</p>}
          </div>

          {/* Initial capital */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="rerun-capital" className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              Initial Capital (₹)
            </label>
            <input
              id="rerun-capital"
              type="number"
              value={capital}
              min={100_000}
              step={100_000}
              onChange={(e) => { setCapital(Number(e.target.value)); setCapitalErr(null) }}
              disabled={submitDisabled}
              className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-mono bg-paper text-ink-primary focus:outline-none focus:border-accent disabled:opacity-60"
            />
            {capitalErr
              ? <p className="font-sans text-xs text-signal-neg">{capitalErr}</p>
              : <p className="font-sans text-xs text-ink-tertiary">
                  {capital > 0 ? `₹${capital.toLocaleString('en-IN')}` : ''}
                </p>
            }
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={handleClose}
              disabled={isPending}
              className="font-sans text-sm text-ink-secondary hover:text-ink-primary disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitDisabled}
              className="bg-accent text-paper font-sans text-sm px-4 py-2 rounded-[2px] hover:opacity-90 disabled:opacity-50"
            >
              {isPending ? 'Submitting…' : isRunning ? 'Running…' : 'Re-run Backtest'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
