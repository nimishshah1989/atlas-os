'use client'
import { useState } from 'react'
import { StageBadge, SignalBadge } from './CTSSignalBadge'

type Signal = 'PPC' | 'NPC' | 'Contraction' | null

function sectionTitle(stage: number | null, signal: Signal): string {
  if (stage === 2 && signal === 'PPC') return 'Stage 2 · PPC Setup'
  if (stage === 2 && signal === 'Contraction') return 'Stage 2 · Contracting'
  if (stage === 2 && signal === 'NPC') return 'Stage 2 · NPC Warning'
  if (stage === 2) return 'Stage 2 · Advancing'
  if (signal) return `Stage ${stage ?? '?'} · ${signal}`
  return 'Timing Setup'
}

export function CTSDeepDiveCard({
  symbol,
  stage,
  signal,
  signalDate,
  triggerLevel,
}: {
  symbol: string
  stage: number | null
  signal: Signal
  signalDate?: string | null
  triggerLevel?: number | null
}) {
  const [brief, setBrief] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const requestBrief = async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/cts-brief`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setBrief(data.brief)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border border-paper-rule rounded-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-paper-rule">
        <h3 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          {sectionTitle(stage, signal)}
        </h3>
        <button
          onClick={requestBrief}
          disabled={loading}
          className="font-sans text-xs text-accent hover:text-ink-secondary disabled:opacity-40 min-h-[32px] px-1 flex items-center"
        >
          {loading ? 'Generating…' : 'Request Brief'}
        </button>
      </div>

      {/* Signal strip — always visible, static data */}
      <div className="flex items-stretch">
        <div className="flex flex-col gap-1 px-3 py-2.5 border-r border-paper-rule">
          <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Stage
          </span>
          <StageBadge stage={stage as 1 | 2 | 3 | 4 | null} />
        </div>
        <div className="flex flex-col gap-1 px-3 py-2.5 border-r border-paper-rule">
          <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Signal
          </span>
          <SignalBadge signal={signal} date={signalDate ?? undefined} />
        </div>
        {triggerLevel != null && (
          <div className="flex flex-col gap-1 px-3 py-2.5">
            <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
              Trigger
            </span>
            <span className="font-mono text-sm text-ink-primary">₹{triggerLevel.toFixed(2)}</span>
          </div>
        )}
      </div>

      {/* Brief area — only appears after request */}
      {loading && (
        <div className="px-3 py-3 border-t border-paper-rule space-y-2 animate-pulse">
          <div className="h-2.5 bg-paper-rule/40 rounded-full w-full" />
          <div className="h-2.5 bg-paper-rule/40 rounded-full w-4/5" />
          <div className="h-2.5 bg-paper-rule/40 rounded-full w-3/5" />
        </div>
      )}

      {error && !loading && (
        <div className="px-3 py-3 border-t border-paper-rule">
          <p className="font-sans text-xs text-ink-tertiary">
            Brief unavailable — please try again.
          </p>
        </div>
      )}

      {brief && !loading && !error && (
        <div className="px-3 py-3 border-t border-paper-rule space-y-2">
          <p className="font-sans text-xs text-ink-primary leading-relaxed">{brief}</p>
          <p className="font-sans text-[10px] text-ink-tertiary">
            Generated from Atlas signals · Not investment advice · SEBI-compliant
          </p>
        </div>
      )}
    </div>
  )
}
