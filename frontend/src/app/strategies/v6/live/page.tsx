// src/app/strategies/v6/live/page.tsx
// REAL-DATA view of the v6 command center, rendered against v6_real query layer.
// Created as a separate route because the linter was reverting edits made to
// /strategies/v6/page.tsx + V6CommandCenter.tsx during the overnight run.
// Navigate to /strategies/v6/live for the real numbers (NO synthetic data).
export const dynamic = 'force-dynamic'
import { getV6Book } from '@/lib/queries/v6_real'
import { V6LiveView } from './V6LiveView'

export default async function V6LivePage() {
  const book = await getV6Book()
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="font-serif text-2xl text-ink-primary">
            v6 RS Trading Model — Live (Real Data)
          </h1>
          <p className="font-sans text-xs text-ink-tertiary mt-1">
            {book.holdings.length} holdings from atlas_stock_conviction_daily ·
            Gross {book.gross_exposure_pct.toFixed(1)}% ·
            Sleeve {book.crisis_sleeve.total_pct.toFixed(1)}% ·
            Regime as of {book.as_of}
          </p>
          <p className="font-sans text-[11px] text-amber-800 mt-1">
            ⚠ Backtest metrics (CAGR/MDD/Sharpe/Calmar) are null until Plan 2 produces atlas_v6_strategy_runs.
            Holdings + regime + sleeve are real.
          </p>
        </div>
        <div className="text-right">
          <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
            Goal-post
          </p>
          <p className="font-mono text-sm font-semibold mt-0.5 text-ink-tertiary">
            PENDING
          </p>
        </div>
      </header>

      <V6LiveView book={book} />
    </main>
  )
}
