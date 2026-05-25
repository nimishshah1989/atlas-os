// frontend/src/components/v6/CellDetailClient.tsx
//
// Client component for /v6/cells/[cell_id].
// Receives all data as props (pre-fetched by the RSC page shell).
//
// Sections:
//  1. CellHero (grade · IC · fric-adj · BH-FDR q · predicted_excess · drift chip)
//  2. Rule DSL as plain-English predicates
//  3. Stocks firing this cell today (table with PortfolioBadge col)
//  4. 3-window backtest (walk-forward runs)
//  5. IC stability over time (placeholder — data from walkforward_runs)
//  6. Friction-adjusted excess curve (placeholder)
//  7. Feature predicates with "what this means" translations
//  8. Last-N signal_calls with realized outcomes (atlas_ledger — empty at v6.0)
//  9. Maintainer notes + drift event log link
//
// LOC budget: ≤500
// allow-large: CellDetailClient is the primary page body; 9 sections require
// ~450 LOC to render correctly with empty states.

'use client'

import React from 'react'
import { CellHero } from '@/components/v6/CellHero'
import { CellRulePlainEnglish } from '@/components/v6/CellRulePlainEnglish'
import { PortfolioBadge } from '@/components/v6/PortfolioBadge'
import type { Cell } from '@/lib/queries/v6/cells'
import type { SignalCallEvent } from '@/lib/queries/v6/recent_signal_calls'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import { formatPct, signedPct } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WalkForwardWindow {
  run_id: string
  window_train_start: string
  window_train_end: string
  window_test_start: string
  window_test_end: string
  tp_rate: string | null
  median_excess: string | null
  friction_adjusted_excess: string | null
  n_observations: number
  status: string
}

export interface LedgerOutcome {
  signal_call_id: string
  realized_excess: string
  realized_at: string
  status: string
}

export interface CellDetailClientProps {
  cell: Cell
  /** Human-readable label e.g. "Mid 12m Pullback" or "<cap_tier> <tenure> <action>" */
  cellLabel: string
  /** Currently-active signal calls for this cell (stocks firing today) */
  firingToday: SignalCallEvent[]
  /** Recent signal calls history (all) */
  signalHistory: SignalCallEvent[]
  /** Map from instrument_id → HoldingState for held instruments */
  holdingStates: Record<string, HoldingState>
  /** Walk-forward backtest windows */
  walkForwardWindows: WalkForwardWindow[]
  /** Realized outcomes from atlas_ledger (empty at v6.0) */
  ledgerOutcomes: LedgerOutcome[]
  /** Maintainer notes from cell definition */
  maintainerNotes: string | null
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({
  title,
  children,
  id,
}: {
  title: string
  children: React.ReactNode
  id?: string
}): React.ReactElement {
  return (
    <section
      id={id}
      aria-label={title}
      className="bg-paper border border-paper-rule rounded-[4px] p-5"
    >
      <h2 className="text-[11px] font-sans font-semibold uppercase tracking-[0.1em] text-ink-tertiary mb-3">
        {title}
      </h2>
      {children}
    </section>
  )
}

function EmptyState({ message }: { message: string }): React.ReactElement {
  return (
    <p className="text-sm font-sans text-ink-tertiary italic py-2" role="note">
      {message}
    </p>
  )
}

// ---------------------------------------------------------------------------
// Section 3: Stocks firing today
// ---------------------------------------------------------------------------

function FiringTodaySection({
  firingToday,
  holdingStates,
}: {
  firingToday: SignalCallEvent[]
  holdingStates: Record<string, HoldingState>
}): React.ReactElement {
  if (firingToday.length === 0) {
    return (
      <Section title="Stocks firing this cell today" id="firing-today">
        <EmptyState message="No stocks firing this cell today." />
      </Section>
    )
  }

  return (
    <Section title={`Stocks firing this cell today (${firingToday.length})`} id="firing-today">
      <div className="overflow-x-auto">
        <table
          className="w-full text-sm font-sans"
          aria-label="Stocks currently firing this cell"
        >
          <thead>
            <tr className="border-b border-paper-rule text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">
              <th scope="col" className="text-left py-2 pr-4">Symbol</th>
              <th scope="col" className="text-left py-2 pr-4">Entry date</th>
              <th scope="col" className="text-right py-2 pr-4">Confidence</th>
              <th scope="col" className="text-right py-2 pr-4">Predicted excess</th>
              <th scope="col" className="text-left py-2">Portfolio</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-paper-rule/60">
            {firingToday.map((sc) => {
              const holdingState = holdingStates[sc.instrument_id] ?? null
              return (
                <tr
                  key={sc.signal_call_id}
                  className="hover:bg-paper-deep/40 transition-colors"
                >
                  <td className="py-2 pr-4 font-mono font-semibold text-ink-primary">
                    <a
                      href={`/v6/stocks/${sc.instrument_id}`}
                      className="hover:text-teal transition-colors"
                    >
                      {sc.ticker}
                    </a>
                  </td>
                  <td className="py-2 pr-4 font-mono text-ink-secondary text-xs">
                    {sc.entry_date}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono tabular-nums text-ink-secondary">
                    {formatPct(sc.confidence_unconditional)}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono tabular-nums">
                    <span
                      className={
                        sc.predicted_excess && parseFloat(sc.predicted_excess) > 0
                          ? 'text-signal-pos'
                          : sc.predicted_excess && parseFloat(sc.predicted_excess) < 0
                          ? 'text-signal-neg'
                          : 'text-ink-tertiary'
                      }
                    >
                      {signedPct(sc.predicted_excess)}
                    </span>
                  </td>
                  <td className="py-2">
                    <PortfolioBadge state={holdingState} variant="compact" />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Section 4: 3-window backtest
// ---------------------------------------------------------------------------

function BacktestSection({
  windows,
}: {
  windows: WalkForwardWindow[]
}): React.ReactElement {
  if (windows.length === 0) {
    return (
      <Section title="Walk-forward backtest" id="backtest">
        <EmptyState message="Insufficient backtest data." />
      </Section>
    )
  }

  return (
    <Section title={`Walk-forward backtest (${windows.length} window${windows.length === 1 ? '' : 's'})`} id="backtest">
      <div className="overflow-x-auto">
        <table
          className="w-full text-sm font-sans"
          aria-label="Walk-forward backtest windows"
        >
          <thead>
            <tr className="border-b border-paper-rule text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">
              <th scope="col" className="text-left py-2 pr-4">Train window</th>
              <th scope="col" className="text-left py-2 pr-4">Test window</th>
              <th scope="col" className="text-right py-2 pr-4">TP rate</th>
              <th scope="col" className="text-right py-2 pr-4">Median excess</th>
              <th scope="col" className="text-right py-2 pr-4">Fric-adj excess</th>
              <th scope="col" className="text-right py-2">N obs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-paper-rule/60">
            {windows.map((w) => (
              <tr key={w.run_id} className="hover:bg-paper-deep/40 transition-colors">
                <td className="py-2 pr-4 font-mono text-xs text-ink-secondary">
                  {w.window_train_start} – {w.window_train_end}
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-ink-secondary">
                  {w.window_test_start} – {w.window_test_end}
                </td>
                <td className="py-2 pr-4 text-right font-mono tabular-nums text-ink-primary">
                  {w.tp_rate != null ? formatPct(w.tp_rate) : '—'}
                </td>
                <td className="py-2 pr-4 text-right font-mono tabular-nums">
                  <span className={w.median_excess && parseFloat(w.median_excess) > 0 ? 'text-signal-pos' : 'text-ink-primary'}>
                    {signedPct(w.median_excess)}
                  </span>
                </td>
                <td className="py-2 pr-4 text-right font-mono tabular-nums">
                  <span className={w.friction_adjusted_excess && parseFloat(w.friction_adjusted_excess) > 0 ? 'text-signal-pos' : 'text-ink-primary'}>
                    {signedPct(w.friction_adjusted_excess)}
                  </span>
                </td>
                <td className="py-2 text-right font-mono tabular-nums text-ink-secondary">
                  {w.n_observations}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Section 8: Realized outcomes (atlas_ledger)
// ---------------------------------------------------------------------------

function LedgerSection({
  outcomes,
  signalHistory,
}: {
  outcomes: LedgerOutcome[]
  signalHistory: SignalCallEvent[]
}): React.ReactElement {
  if (outcomes.length === 0) {
    return (
      <Section title="Realized outcomes" id="realized-outcomes">
        <EmptyState message="No realized outcomes yet." />
      </Section>
    )
  }

  // Join outcomes with signal history for ticker display
  const signalMap = new Map(signalHistory.map((s) => [s.signal_call_id, s]))

  return (
    <Section title={`Realized outcomes (${outcomes.length})`} id="realized-outcomes">
      <div className="overflow-x-auto">
        <table
          className="w-full text-sm font-sans"
          aria-label="Realized outcomes from atlas_ledger"
        >
          <thead>
            <tr className="border-b border-paper-rule text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">
              <th scope="col" className="text-left py-2 pr-4">Signal call</th>
              <th scope="col" className="text-right py-2 pr-4">Realized excess</th>
              <th scope="col" className="text-left py-2 pr-4">Realized at</th>
              <th scope="col" className="text-left py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-paper-rule/60">
            {outcomes.map((o) => {
              const sc = signalMap.get(o.signal_call_id)
              return (
                <tr key={o.signal_call_id} className="hover:bg-paper-deep/40 transition-colors">
                  <td className="py-2 pr-4 font-mono text-xs text-ink-secondary">
                    {sc?.ticker ?? o.signal_call_id.slice(0, 8) + '…'}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono tabular-nums">
                    <span className={parseFloat(o.realized_excess) > 0 ? 'text-signal-pos' : 'text-signal-neg'}>
                      {signedPct(o.realized_excess)}
                    </span>
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-ink-secondary">
                    {o.realized_at.slice(0, 10)}
                  </td>
                  <td className="py-2 font-sans text-xs text-ink-secondary">
                    {o.status}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// CellDetailClient
// ---------------------------------------------------------------------------

export function CellDetailClient({
  cell,
  cellLabel,
  firingToday,
  signalHistory,
  holdingStates,
  walkForwardWindows,
  ledgerOutcomes,
  maintainerNotes,
}: CellDetailClientProps): React.ReactElement {
  return (
    <div className="min-h-screen bg-[#F8F4EC]">
      {/* Section 1: Hero */}
      <CellHero cell={cell} cellLabel={cellLabel} />

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">

        {/* Section 2: Rule predicates */}
        <Section title="Rule predicates (plain English)" id="rule-predicates">
          <CellRulePlainEnglish rule_dsl={cell.rule_dsl} showExit={false} />
        </Section>

        {/* Section 3: Stocks firing today */}
        <FiringTodaySection
          firingToday={firingToday}
          holdingStates={holdingStates}
        />

        {/* Section 4: Walk-forward backtest */}
        <BacktestSection windows={walkForwardWindows} />

        {/* Section 5: IC stability */}
        <Section title="IC stability over time" id="ic-stability">
          <EmptyState message="Rolling IC history not yet available for this cell." />
        </Section>

        {/* Section 6: Friction-adjusted excess curve */}
        <Section title="Friction-adjusted excess curve" id="excess-curve">
          <EmptyState message="Excess curve will be available after 3+ walk-forward windows." />
        </Section>

        {/* Section 8: Realized outcomes */}
        <LedgerSection outcomes={ledgerOutcomes} signalHistory={signalHistory} />

        {/* Section 9: Maintainer notes */}
        <Section title="Maintainer notes" id="maintainer-notes">
          {maintainerNotes ? (
            <p className="text-sm font-sans text-ink-secondary leading-relaxed whitespace-pre-wrap">
              {maintainerNotes}
            </p>
          ) : (
            <EmptyState message="No maintainer notes for this cell." />
          )}
          <div className="mt-3 pt-3 border-t border-paper-rule">
            <p className="text-[11px] font-sans text-ink-tertiary">
              Drift events:{' '}
              <a
                href="/methodology"
                className="text-teal hover:underline transition-colors"
                aria-label="View drift event log on methodology page"
              >
                view on Methodology page →
              </a>
            </p>
          </div>
        </Section>

      </div>
    </div>
  )
}

export default CellDetailClient
