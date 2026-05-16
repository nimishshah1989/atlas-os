'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Info, X } from 'lucide-react'
import type { FundDecisionScoreRow } from '@/lib/queries/funds'

function scoreColor(score: number): string {
  if (score >= 65) return '#1D9E75'
  if (score >= 35) return '#f59e0b'
  return '#ef4444'
}

function scoreLabel(score: number): string {
  if (score >= 65) return 'Sharp'
  if (score >= 35) return 'Average'
  return 'Poor'
}

function ScoreFormulaPanel({ onClose }: { onClose: () => void }) {
  return (
    <div className="bg-paper border border-paper-rule rounded p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-sans text-xs font-semibold text-ink-primary">
          How Decision Score is Calculated
        </div>
        <button type="button" onClick={onClose} className="text-ink-tertiary hover:text-ink-secondary">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="bg-paper-rule/10 border border-paper-rule rounded px-3 py-2.5">
        <div className="font-mono text-[11px] text-ink-secondary">
          score = (high_decisions − low_decisions) ÷ total × 50 + 50
        </div>
        <div className="font-sans text-[10px] text-ink-tertiary mt-1">
          Range 0–100. Neutral manager = 50. All-good = 100. All-bad = 0.
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
        <div>
          <div className="font-sans text-[10px] font-semibold text-signal-pos mb-1.5">
            High quality — adds to score
          </div>
          <div className="space-y-1">
            <div className="font-sans text-[10px] text-ink-secondary flex gap-1.5">
              <span className="text-signal-pos shrink-0">●</span>
              <span>Bought a stock in <strong>Strong</strong> or <strong>Leader</strong> RS state</span>
            </div>
            <div className="font-sans text-[10px] text-ink-secondary flex gap-1.5">
              <span className="text-signal-pos shrink-0">●</span>
              <span>Sold a stock in <strong>Weak</strong> or <strong>Declining</strong> RS state</span>
            </div>
          </div>
        </div>
        <div>
          <div className="font-sans text-[10px] font-semibold text-signal-neg mb-1.5">
            Low quality — subtracts from score
          </div>
          <div className="space-y-1">
            <div className="font-sans text-[10px] text-ink-secondary flex gap-1.5">
              <span className="text-signal-neg shrink-0">●</span>
              <span>Bought a stock in <strong>Weak</strong> or <strong>Declining</strong> RS state</span>
            </div>
            <div className="font-sans text-[10px] text-ink-secondary flex gap-1.5">
              <span className="text-signal-neg shrink-0">●</span>
              <span>Sold a stock in <strong>Strong</strong> or <strong>Leader</strong> RS state</span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex gap-4 pt-2 border-t border-paper-rule">
        <span className="font-sans text-[10px]">
          <span className="text-signal-pos font-semibold">Sharp</span> ≥65
        </span>
        <span className="font-sans text-[10px]">
          <span className="text-signal-warn font-semibold">Average</span> 35–65
        </span>
        <span className="font-sans text-[10px]">
          <span className="text-signal-neg font-semibold">Poor</span> &lt;35
        </span>
      </div>

      <div className="font-sans text-[10px] text-ink-tertiary pt-2 border-t border-paper-rule space-y-1">
        <p>
          RS state is captured at the time of each portfolio disclosure. Only{' '}
          <strong>new entries</strong> and <strong>full exits</strong> count toward the score —
          position size changes (increases/decreases) and the very first snapshot are excluded.
        </p>
        <p>A minimum of 3 buy/sell events per disclosure period is required to produce a score.</p>
      </div>
    </div>
  )
}

type Props = {
  scores: FundDecisionScoreRow[]
  mstar_id: string
}

export function FundManagerDecisionSummary({ scores, mstar_id }: Props) {
  const [showFormula, setShowFormula] = useState(false)

  if (scores.length === 0) {
    return <p className="font-sans text-sm text-ink-secondary">No decision history available.</p>
  }

  const latest = scores[0]
  const scoredPeriods = scores.filter((s) => s.signal_score !== null)

  return (
    <div className="space-y-5">
      {/* Latest period summary */}
      <div className="flex items-start gap-4 flex-wrap">
        {/* Score block */}
        <div className="flex items-center gap-3">
          {latest.signal_score !== null ? (
            <>
              <div
                className="w-10 h-10 rounded flex items-center justify-center font-mono text-base font-bold text-white shrink-0"
                style={{ backgroundColor: scoreColor(Number(latest.signal_score)) }}
              >
                {Number(latest.signal_score).toFixed(0)}
              </div>
              <div>
                <div
                  className="font-sans text-sm font-semibold"
                  style={{ color: scoreColor(Number(latest.signal_score)) }}
                >
                  {latest.decision_state}
                </div>
                <div className="font-sans text-[10px] text-ink-tertiary">
                  Latest period · {latest.period_date}
                </div>
              </div>
            </>
          ) : (
            <div>
              <div className="font-sans text-xs text-ink-secondary">Not yet scored</div>
              <div className="font-sans text-[10px] text-ink-tertiary">
                {latest.period_date} · need ≥3 buys/sells
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowFormula((v) => !v)}
            className="flex items-center gap-1 text-ink-tertiary hover:text-teal-600 font-sans text-[10px] ml-2"
            title="How is decision score calculated?"
          >
            <Info className="w-3 h-3" />
            How scored?
          </button>
        </div>

        {/* Activity counts */}
        <div className="flex items-center gap-4 font-sans text-[11px] ml-auto flex-wrap">
          <span title="New positions opened this period (scored)">
            <span className="font-semibold text-signal-pos">{latest.entries_count}</span>
            <span className="text-ink-tertiary ml-1">buys</span>
          </span>
          <span title="Positions fully closed this period (scored)">
            <span className="font-semibold text-signal-neg">{latest.exits_count}</span>
            <span className="text-ink-tertiary ml-1">sells</span>
          </span>
          <span title="Existing positions with increased weight (not scored)">
            <span className="font-semibold text-blue-500">{latest.increases_count}</span>
            <span className="text-ink-tertiary ml-1">adds</span>
          </span>
          <span title="Existing positions with reduced weight (not scored)">
            <span className="font-semibold text-orange-500">{latest.decreases_count}</span>
            <span className="text-ink-tertiary ml-1">trims</span>
          </span>
          <Link
            href={`/funds/${mstar_id}/decisions`}
            className="font-sans text-[11px] text-teal-600 hover:underline"
          >
            Full history →
          </Link>
        </div>
      </div>

      {/* Formula explanation panel */}
      {showFormula && <ScoreFormulaPanel onClose={() => setShowFormula(false)} />}

      {/* Scored periods timeline */}
      {scoredPeriods.length === 0 ? (
        <div className="bg-paper-rule/5 border border-paper-rule rounded px-4 py-3 font-sans text-[11px] text-ink-tertiary space-y-1">
          <p>
            <span className="font-semibold text-ink-secondary">No scored periods yet.</span> A minimum of 3
            new buy or sell events per disclosure period is required. Most funds make only 1–2 new
            entries or exits per monthly disclosure — scores will appear as portfolio turnover accumulates.
          </p>
        </div>
      ) : (
        <div>
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">
            Scored disclosure periods
          </div>

          <div className="grid grid-cols-[100px_1fr_90px_52px_90px] gap-x-3 px-1 mb-1.5">
            {['Period', 'Score (0=bad · 50=neutral · 100=good)', 'State', 'B/S', '1m outcome'].map(
              (h) => (
                <div key={h} className="font-sans text-[9px] text-ink-tertiary uppercase tracking-wider">
                  {h}
                </div>
              ),
            )}
          </div>

          <div className="space-y-1.5">
            {scoredPeriods.map((s) => {
              const score = Number(s.signal_score)
              const color = scoreColor(score)
              return (
                <div
                  key={s.period_date}
                  className="grid grid-cols-[100px_1fr_90px_52px_90px] gap-x-3 items-center px-1 py-1 rounded-sm hover:bg-paper-rule/10"
                >
                  <span className="font-mono text-[10px] text-ink-secondary">{s.period_date}</span>

                  {/* Score bar — midline at 50% marks neutral */}
                  <div className="relative h-2 bg-paper-rule/25 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${score}%`, backgroundColor: color }}
                    />
                    <div
                      className="absolute top-0 bottom-0 w-px bg-ink-tertiary/40"
                      style={{ left: '50%' }}
                    />
                  </div>

                  <div className="flex items-center gap-1">
                    <span className="font-mono text-[11px] font-semibold" style={{ color }}>
                      {score.toFixed(0)}
                    </span>
                    <span className="font-sans text-[10px]" style={{ color }}>
                      {scoreLabel(score)}
                    </span>
                  </div>

                  <span
                    className="font-sans text-[10px] text-ink-tertiary"
                    title={`${s.entries_count} buys, ${s.exits_count} sells`}
                  >
                    {s.entries_count}B {s.exits_count}S
                  </span>

                  <span className="font-sans text-[10px] text-right">
                    {s.outcome_score_1m !== null ? (
                      <span style={{ color: scoreColor(Number(s.outcome_score_1m)) }}>
                        {Number(s.outcome_score_1m).toFixed(0)}
                      </span>
                    ) : (
                      <span className="text-ink-tertiary/50 italic">pending</span>
                    )}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
