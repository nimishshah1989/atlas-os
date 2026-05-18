'use client'
// src/app/strategies/v6/V6CommandCenter.tsx
// Client island: KPI band + regime panel + crisis sleeve + holdings table +
// last-rebalance + goal-post status. Visual language matches atlas-os strategies
// page (paper bg, ink-primary, font-serif headings, font-mono numbers).
// allow-large: command-center page intentionally aggregates 6 panels of state.

import { useState } from 'react'
import type { V6BookSnapshot, V6Holding, ConfidenceBand } from '@/lib/queries/v6'

type Props = { book: V6BookSnapshot }

const REGIME_BG: Record<string, string> = {
  calm: 'bg-emerald-50 text-emerald-900 border-emerald-200',
  normal: 'bg-paper text-ink-primary border-paper-rule',
  yellow: 'bg-amber-50 text-amber-900 border-amber-200',
  orange: 'bg-orange-50 text-orange-900 border-orange-200',
  red: 'bg-rose-50 text-rose-900 border-rose-200',
  crash: 'bg-rose-100 text-rose-950 border-rose-300',
}

const CONFIDENCE_PILL: Record<ConfidenceBand, string> = {
  HIGH: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  MED: 'bg-amber-50 text-amber-800 border-amber-200',
  LOW: 'bg-stone-100 text-stone-700 border-stone-200',
}

function pct(n: number, signed = false): string {
  const s = `${n.toFixed(1)}%`
  return signed && n > 0 ? `+${s}` : s
}

function inr(cr: number): string {
  return `₹${cr.toLocaleString('en-IN')} cr`
}

export function V6CommandCenter({ book }: Props) {
  const [holdingsSort, setHoldingsSort] = useState<'composite' | 'weight' | 'pnl'>('composite')

  const sortedHoldings = [...book.holdings].sort((a, b) => {
    if (holdingsSort === 'weight') return b.weight_pct - a.weight_pct
    if (holdingsSort === 'pnl') return b.pnl_since_entry_pct - a.pnl_since_entry_pct
    return b.composite_score - a.composite_score
  })

  return (
    <div className="space-y-6">
      {/* KPI Band — six headline numbers */}
      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Kpi label="Net CAGR"     value={pct(book.cagr_net_pct)}        tone="strong" />
        <Kpi label="Max Drawdown" value={pct(-book.max_drawdown_pct)}    tone="loss" />
        <Kpi label="Vol (ann)"    value={pct(book.vol_annualized_pct)}   tone="neutral" />
        <Kpi label="Sharpe (net)" value={book.sharpe_net.toFixed(2)}     tone="strong" />
        <Kpi label="Calmar"       value={book.calmar.toFixed(2)}         tone={book.calmar >= 1 ? 'strong' : 'neutral'} />
        <Kpi label="Capacity"     value={inr(book.capacity_cr)}          tone="neutral" />
      </section>

      {/* Row: Regime + Crisis Sleeve + Exposure */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Panel title="Macro Regime" subtitle={`Score ${book.regime.score}/5 · Gross ${book.regime.gross_multiplier.toFixed(2)}×`}>
          <div className={`px-3 py-2 mb-3 border rounded-[2px] ${REGIME_BG[book.regime.level]}`}>
            <p className="font-sans text-[11px] uppercase tracking-wide">Current</p>
            <p className="font-serif text-lg font-semibold">{book.regime.level.toUpperCase()}</p>
          </div>
          <ul className="space-y-2">
            {book.regime.signals.map((s) => (
              <li key={s.name} className="flex items-baseline justify-between">
                <span className="font-sans text-xs text-ink-primary">{s.name}</span>
                <span className={`font-mono text-[11px] ${s.firing ? 'text-rose-700' : 'text-ink-tertiary'}`}>
                  {s.firing ? '● ' : '○ '}{s.reading}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Crisis Sleeve" subtitle={`${book.crisis_sleeve.total_pct.toFixed(1)}% of book · cross-asset TSMOM`}>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-ink-tertiary border-b border-paper-rule">
                <th className="text-left font-sans font-normal py-1">Asset</th>
                <th className="text-right font-sans font-normal py-1">Weight</th>
                <th className="text-right font-sans font-normal py-1">12m TSMOM</th>
              </tr>
            </thead>
            <tbody>
              {book.crisis_sleeve.legs.map((l) => (
                <tr key={l.symbol} className="border-b border-paper-rule/40">
                  <td className="py-1.5">
                    <p className="font-mono text-ink-primary">{l.symbol}</p>
                    <p className="font-sans text-[10px] text-ink-tertiary">{l.name}</p>
                  </td>
                  <td className="text-right font-mono">{pct(l.weight_pct)}</td>
                  <td className={`text-right font-mono ${l.tsmom_12m_return_pct > 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {pct(l.tsmom_12m_return_pct, true)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Exposure" subtitle="Where the book is allocated right now">
          <ExposureBar
            equity={book.gross_exposure_pct - book.crisis_sleeve.total_pct}
            sleeve={book.crisis_sleeve.total_pct}
            cash={book.cash_pct}
          />
          <dl className="mt-4 grid grid-cols-3 gap-2 text-xs">
            <Stat label="Equity book" value={pct(book.gross_exposure_pct - book.crisis_sleeve.total_pct)} />
            <Stat label="Crisis sleeve" value={pct(book.crisis_sleeve.total_pct)} />
            <Stat label="Cash" value={pct(book.cash_pct)} />
          </dl>
        </Panel>
      </section>

      {/* Holdings Table */}
      <section>
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="font-serif text-lg text-ink-primary">Holdings ({book.holdings.length})</h2>
          <div className="flex gap-2">
            {(['composite', 'weight', 'pnl'] as const).map((k) => (
              <button
                key={k}
                onClick={() => setHoldingsSort(k)}
                className={`px-2.5 py-1 font-sans text-[11px] uppercase tracking-wide rounded-[2px] border ${
                  holdingsSort === k
                    ? 'bg-ink-primary text-paper border-ink-primary'
                    : 'bg-paper text-ink-secondary border-paper-rule hover:border-ink-tertiary'
                }`}
              >
                Sort: {k}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden">
          <table className="w-full text-xs">
            <thead className="border-b border-paper-rule bg-paper-rule/20">
              <tr className="text-ink-tertiary">
                <th className="text-left font-sans font-normal px-3 py-2">Symbol</th>
                <th className="text-left font-sans font-normal px-3 py-2">Sector</th>
                <th className="text-right font-sans font-normal px-3 py-2">Composite</th>
                <th className="text-right font-sans font-normal px-3 py-2">Weight</th>
                <th className="text-right font-sans font-normal px-3 py-2">Days held</th>
                <th className="text-right font-sans font-normal px-3 py-2">P&amp;L</th>
                <th className="text-center font-sans font-normal px-3 py-2">Confidence</th>
                <th className="text-center font-sans font-normal px-3 py-2">Cluster</th>
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map((h) => (
                <HoldingRow key={h.symbol} h={h} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Last Rebalance */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Entered Last Rebalance" subtitle={book.last_rebalance.date}>
          <ul className="divide-y divide-paper-rule/50">
            {book.last_rebalance.entered.map((e) => (
              <li key={e.symbol} className="py-2 flex items-baseline justify-between">
                <div>
                  <p className="font-mono text-sm text-ink-primary">{e.symbol}</p>
                  <p className="font-sans text-[11px] text-ink-tertiary">{e.reason}</p>
                </div>
                <span className="font-mono text-xs text-emerald-700">+{e.weight_pct.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Exited Last Rebalance" subtitle={book.last_rebalance.date}>
          <ul className="divide-y divide-paper-rule/50">
            {book.last_rebalance.exited.map((e) => (
              <li key={e.symbol} className="py-2 flex items-baseline justify-between">
                <div>
                  <p className="font-mono text-sm text-ink-primary">{e.symbol}</p>
                  <p className="font-sans text-[11px] text-ink-tertiary">{e.reason}</p>
                </div>
                <span className="font-mono text-xs text-rose-700">EXIT</span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>

      {/* Goal-Post Status */}
      <section>
        <Panel title="Goal-Post Constraints" subtitle={`${book.goal_post.constraints.filter((c) => c.pass).length} of ${book.goal_post.constraints.length} passing`}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {book.goal_post.constraints.map((c) => (
              <div
                key={c.name}
                className={`px-3 py-2 border rounded-[2px] ${
                  c.pass ? 'border-emerald-200 bg-emerald-50/50' : 'border-amber-200 bg-amber-50/50'
                }`}
              >
                <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">{c.name}</p>
                <p className="font-mono text-xs text-ink-primary mt-0.5">
                  {c.actual}
                  <span className="text-ink-tertiary ml-1.5">/ {c.target}</span>
                </p>
              </div>
            ))}
          </div>
        </Panel>
      </section>
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: 'strong' | 'neutral' | 'loss' }) {
  const toneClass =
    tone === 'strong' ? 'text-emerald-800' : tone === 'loss' ? 'text-rose-800' : 'text-ink-primary'
  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
      <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">{label}</p>
      <p className={`font-mono text-lg font-semibold mt-1 ${toneClass}`}>{value}</p>
    </div>
  )
}

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
      <h3 className="font-serif text-base text-ink-primary">{title}</h3>
      {subtitle && <p className="font-sans text-[11px] text-ink-tertiary mt-0.5 mb-3">{subtitle}</p>}
      {children}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">{label}</dt>
      <dd className="font-mono text-sm text-ink-primary mt-0.5">{value}</dd>
    </div>
  )
}

function ExposureBar({ equity, sleeve, cash }: { equity: number; sleeve: number; cash: number }) {
  return (
    <div className="w-full h-3 flex rounded-[2px] overflow-hidden border border-paper-rule">
      <div className="bg-emerald-700" style={{ width: `${equity}%` }} title={`Equity ${equity.toFixed(1)}%`} />
      <div className="bg-amber-500" style={{ width: `${sleeve}%` }} title={`Sleeve ${sleeve.toFixed(1)}%`} />
      <div className="bg-stone-200" style={{ width: `${cash}%` }} title={`Cash ${cash.toFixed(1)}%`} />
    </div>
  )
}

function HoldingRow({ h }: { h: V6Holding }) {
  return (
    <tr className="border-b border-paper-rule/40 hover:bg-paper-rule/10">
      <td className="px-3 py-2">
        <p className="font-mono text-ink-primary">{h.symbol}</p>
        <p className="font-sans text-[10px] text-ink-tertiary">{h.name}</p>
      </td>
      <td className="px-3 py-2 font-sans text-ink-secondary">{h.sector}</td>
      <td className="px-3 py-2 text-right font-mono">{h.composite_score.toFixed(2)}</td>
      <td className="px-3 py-2 text-right font-mono">{h.weight_pct.toFixed(1)}%</td>
      <td className="px-3 py-2 text-right font-mono text-ink-tertiary">{h.days_held}</td>
      <td className={`px-3 py-2 text-right font-mono ${h.pnl_since_entry_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
        {pct(h.pnl_since_entry_pct, true)}
      </td>
      <td className="px-3 py-2 text-center">
        <span className={`inline-block px-1.5 py-0.5 text-[10px] font-sans uppercase tracking-wide border rounded-[2px] ${CONFIDENCE_PILL[h.confidence]}`}>
          {h.confidence}
        </span>
      </td>
      <td className="px-3 py-2 text-center font-mono text-[10px] text-ink-tertiary">{h.hrp_cluster}</td>
    </tr>
  )
}
