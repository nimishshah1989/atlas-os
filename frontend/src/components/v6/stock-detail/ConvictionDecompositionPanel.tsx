// Horizontal-bar breakdown of `atlas_stock_conviction_daily.contributing_signals` JSONB.
// Each signal row shows: signal name, weight bar, contribution value.
// Pure server component.

import 'server-only'

export interface ContributingSignal {
  name: string
  weight: number
  contribution: number
}

interface ConvictionDecompositionPanelProps {
  signals: ContributingSignal[]
  /** Final conviction score 0..1 */
  convictionScore: number | null
  /** 'industry_grade' | 'baseline' | 'descriptive_only' */
  confidenceLabel: string | null
  /** Backing information coefficient */
  backingIc: number | null
  /** Tier name e.g. 'tier_1_megacap' */
  tier: string | null
}

function fmtScore(v: number | null): string {
  if (v == null) return '—'
  return v.toFixed(3)
}

function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}

const CONFIDENCE_COLOR: Record<string, string> = {
  industry_grade:   'text-signal-pos',
  baseline:         'text-signal-warn',
  descriptive_only: 'text-ink-3',
}

export function ConvictionDecompositionPanel({
  signals,
  convictionScore,
  confidenceLabel,
  backingIc,
  tier,
}: ConvictionDecompositionPanelProps) {
  // Sort signals by absolute contribution (largest impact first)
  const sorted = [...signals].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  const maxAbs = Math.max(...sorted.map(s => Math.abs(s.contribution)), 0.01)

  return (
    <section className="border border-paper-rule rounded p-4 bg-paper">
      <div className="flex items-center justify-between mb-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          Conviction Decomposition — what's the score made of?
        </p>
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="text-ink-3">Score:</span>
          <span className="font-semibold text-ink">{fmtScore(convictionScore)}</span>
          {tier && <span className="text-ink-3">· {tier.replace('tier_', 'T').replace('_', ' ')}</span>}
          {confidenceLabel && (
            <span className={`${CONFIDENCE_COLOR[confidenceLabel] ?? 'text-ink-3'} text-[10px] uppercase tracking-wider`}>
              {confidenceLabel.replace('_', ' ')}
            </span>
          )}
          {backingIc != null && <span className="text-ink-3">IC {backingIc.toFixed(3)}</span>}
        </div>
      </div>

      {sorted.length === 0 ? (
        <p className="font-sans text-[12px] text-ink-3 italic">
          No contributing-signal breakdown available. Conviction was derived without per-signal weights.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {sorted.map(sig => {
            const widthPct = Math.min(100, (Math.abs(sig.contribution) / maxAbs) * 100)
            const positive = sig.contribution >= 0
            return (
              <li key={sig.name} className="flex items-center gap-3 font-mono text-[11px]">
                <span className="w-[180px] text-ink-3 truncate" title={sig.name}>{sig.name}</span>
                <div className="flex-1 h-[14px] bg-paper-deep rounded-[2px] relative overflow-hidden">
                  <div
                    className={`absolute top-0 bottom-0 ${positive ? 'left-1/2' : 'right-1/2'} ${positive ? 'bg-signal-pos' : 'bg-signal-neg'}`}
                    style={{ width: `${widthPct / 2}%` }}
                  />
                  <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-paper-rule" />
                </div>
                <span className={`w-[55px] text-right font-semibold ${positive ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {fmtPct(sig.contribution)}
                </span>
                <span className="w-[50px] text-right text-ink-3 text-[10px]">w {sig.weight.toFixed(2)}</span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
