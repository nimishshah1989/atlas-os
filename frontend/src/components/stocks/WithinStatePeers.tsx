// frontend/src/components/stocks/WithinStatePeers.tsx
// Mini-table of top-30 peer stocks in the same Weinstein state.
// Current stock row is highlighted. Pure server component.
import type { WithinStatePeer } from '@/lib/queries/states'

interface WithinStatePeersProps {
  peers: WithinStatePeer[]
  /** instrument_id of the stock currently being viewed — highlighted in table. */
  currentInstrumentId: string
  /** e.g. "stage_2c" */
  state: string
}

// ---------------------------------------------------------------------------
// State → human label
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WithinStatePeers({
  peers,
  currentInstrumentId,
  state,
}: WithinStatePeersProps) {
  const label = stateLabel(state)
  // Display top 30 only
  const displayed = peers.slice(0, 30)

  if (peers.length === 0) {
    return (
      <section data-testid="within-state-peers">
        <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Peers in {label}
        </h3>
        <p className="text-xs text-ink-tertiary mt-2">No peers found for this state today.</p>
      </section>
    )
  }

  return (
    <section data-testid="within-state-peers">
      <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
        Peers in {label}
      </h3>
      <p className="text-xs text-ink-tertiary mt-1">
        Top {displayed.length} of {peers.length} {label} stocks today, ranked by within-state-rank.
      </p>

      <div className="overflow-x-auto mt-3">
        <table className="w-full text-xs" data-testid="peers-table">
          <thead>
            <tr className="border-b border-paper-rule text-ink-tertiary">
              <th className="text-left py-2 font-sans font-medium">#</th>
              <th className="text-left py-2 font-sans font-medium">Symbol</th>
              <th className="text-right py-2 font-sans font-medium">RS rank</th>
              <th className="text-right py-2 font-sans font-medium">Dwell</th>
              <th className="text-right py-2 font-sans font-medium">Within-rank</th>
            </tr>
          </thead>
          <tbody>
            {displayed.map((p, idx) => {
              const isCurrent = p.instrument_id === currentInstrumentId
              return (
                <tr
                  key={p.instrument_id}
                  className={[
                    'border-b border-paper-rule',
                    isCurrent
                      ? 'bg-teal/10 font-medium'
                      : 'hover:bg-paper-rule/20',
                  ].join(' ')}
                  data-testid={isCurrent ? 'current-peer-row' : undefined}
                >
                  <td className="py-2 text-ink-tertiary font-mono">{idx + 1}</td>
                  <td className="py-2">{p.symbol}</td>
                  <td className="py-2 text-right font-mono">
                    {(p.rs_rank_12m * 100).toFixed(0)}
                  </td>
                  <td className="py-2 text-right font-mono">{p.dwell_days}d</td>
                  <td className="py-2 text-right font-mono">
                    {p.within_state_rank.toFixed(2)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
