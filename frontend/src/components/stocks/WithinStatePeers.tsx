// frontend/src/components/stocks/WithinStatePeers.tsx
// Collapsible table of sector peers in the same Weinstein state.
// Current stock row is highlighted. Pure server component (native <details>).
import type { WithinStatePeer } from '@/lib/queries/states'

interface WithinStatePeersProps {
  peers: WithinStatePeer[]
  /** instrument_id of the stock currently being viewed — highlighted in table. */
  currentInstrumentId: string
  /** e.g. "stage_2c" */
  state: string
  /** sector the peer list is scoped to, for the header copy. */
  sector: string | null
}

const STATE_LABELS: Record<string, string> = {
  stage_1:      'Stage 1 base',
  stage_2a:     'Stage 2A fresh breakouts',
  stage_2b:     'Stage 2B confirmed',
  stage_2c:     'Stage 2C mature',
  stage_3:      'Stage 3 tops',
  stage_4:      'Stage 4 declines',
  uninvestable: 'Uninvestable',
}

function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state
}

function pctRank(v: number | null): string {
  return v == null ? '—' : Math.round(v * 100).toString()
}

function signedPct(v: number | null, digits = 0): string {
  if (v == null) return '—'
  const p = v * 100
  return `${p >= 0 ? '+' : ''}${p.toFixed(digits)}%`
}

function signClass(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  return v >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

export function WithinStatePeers({
  peers,
  currentInstrumentId,
  state,
  sector,
}: WithinStatePeersProps) {
  const label = stateLabel(state)

  if (peers.length === 0) {
    return (
      <section data-testid="within-state-peers">
        <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Sector peers in {label}
        </h3>
        <p className="text-xs text-ink-tertiary mt-2">
          No {sector ?? ''} peers in this stage today.
        </p>
      </section>
    )
  }

  return (
    <details data-testid="within-state-peers" className="group">
      <summary className="flex items-center gap-2 cursor-pointer list-none select-none">
        <span className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Sector peers in {label}
        </span>
        <span className="font-sans text-[11px] text-ink-tertiary">
          {peers.length} {sector ?? ''} stock{peers.length === 1 ? '' : 's'} at the same stage
        </span>
        <span className="ml-auto font-sans text-[11px] text-teal group-open:hidden">▼ Show</span>
        <span className="ml-auto font-sans text-[11px] text-teal hidden group-open:inline">▲ Hide</span>
      </summary>

      <p className="text-xs text-ink-tertiary mt-2">
        Ranked by within-state rank — comparable {sector ?? ''} companies at the
        same Weinstein stage, so relative strength and trend can be judged like
        against like.
      </p>

      <div className="overflow-x-auto mt-3">
        <table className="w-full text-xs" data-testid="peers-table">
          <thead>
            <tr className="border-b border-paper-rule text-ink-tertiary">
              <th className="text-left py-2 font-sans font-medium">#</th>
              <th className="text-left py-2 font-sans font-medium">Symbol</th>
              <th className="text-left py-2 font-sans font-medium">Industry</th>
              <th className="text-right py-2 font-sans font-medium" title="12-month relative-strength rank vs the universe (0–100).">RS rank</th>
              <th className="text-right py-2 font-sans font-medium" title="Rank within this stage (0–100) — higher = stronger setup.">Stage rank</th>
              <th className="text-right py-2 font-sans font-medium" title="Close relative to the 50-day SMA, signed %.">vs 50-SMA</th>
              <th className="text-right py-2 font-sans font-medium" title="Slope of the 200-day SMA — positive = long-term uptrend.">200-SMA slope</th>
              <th className="text-right py-2 font-sans font-medium" title="Days the stock has been in its current stage.">Dwell</th>
            </tr>
          </thead>
          <tbody>
            {peers.map((p, idx) => {
              const isCurrent = p.instrument_id === currentInstrumentId
              return (
                <tr
                  key={p.instrument_id}
                  className={[
                    'border-b border-paper-rule',
                    isCurrent ? 'bg-teal/10 font-medium' : 'hover:bg-paper-rule/20',
                  ].join(' ')}
                  data-testid={isCurrent ? 'current-peer-row' : undefined}
                >
                  <td className="py-2 text-ink-tertiary font-mono">{idx + 1}</td>
                  <td className="py-2">
                    <a href={`/stocks/${encodeURIComponent(p.symbol)}`} className="hover:text-teal">
                      {p.symbol}
                    </a>
                  </td>
                  <td className="py-2 text-ink-secondary truncate max-w-[160px]" title={p.industry ?? ''}>
                    {p.industry ?? '—'}
                  </td>
                  <td className="py-2 text-right font-mono">{pctRank(p.rs_rank_12m)}</td>
                  <td className="py-2 text-right font-mono">{pctRank(p.within_state_rank)}</td>
                  <td className={`py-2 text-right font-mono ${signClass(p.close_vs_sma_50)}`}>
                    {signedPct(p.close_vs_sma_50)}
                  </td>
                  <td className={`py-2 text-right font-mono ${signClass(p.sma_200_slope)}`}>
                    {signedPct(p.sma_200_slope, 1)}
                  </td>
                  <td className="py-2 text-right font-mono">{p.dwell_days}d</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}
