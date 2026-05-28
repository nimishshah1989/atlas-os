'use client'
// frontend/src/components/v6/landing/TodayConvictionTabs.tsx
//
// 3-tab "Today's conviction" panel for Market Regime landing (Page 01).
//
// Tabs: Stocks | Funds | ETFs  (mockup order: 01-market-regime.html:893-895)
// Each tab shows top conviction calls as a list: symbol, name/sector,
// cell label, confidence bar (stocks/ETFs) or quality badge (funds), action badge, predicted excess.
//
// Matches mockup 01-market-regime.html section "TODAY'S CONVICTION (3 tabs)".
// Client component — tab selection is the only interactive state.

import { useState } from 'react'
import Link from 'next/link'
import { ActionBadge } from '@/components/v6/shared/ActionBadge'
import type { ConvictionCallRow, ConvictionCallsResult } from '@/lib/queries/v6/landing'

type TabKey = 'stocks' | 'funds' | 'etfs'

type Props = {
  data: ConvictionCallsResult
}

// ---------------------------------------------------------------------------
// Confidence bar — for stocks and ETFs only (signal conviction probability)
// ---------------------------------------------------------------------------

function ConfidenceBar({ value, action }: { value: number; action: string }) {
  const fillClass =
    action === 'NEGATIVE' ? 'bg-signal-neg' :
    action === 'NEUTRAL'  ? 'bg-signal-warn' :
    'bg-signal-pos'

  const pct = Math.min(100, Math.max(0, Math.round(value * 100)))

  return (
    <div
      className="h-1.5 rounded-[1px] overflow-hidden bg-paper-deep"
      role="meter"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Confidence: ${pct}%`}
    >
      <div
        className={`h-full rounded-[1px] transition-all ${fillClass}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Quality badge — for funds only (replaces confidence bar)
// Atlas Leader designation is a boolean label, not a probability.
// ---------------------------------------------------------------------------

function FundQualityBadge({ is_atlas_leader }: { is_atlas_leader: boolean }) {
  if (is_atlas_leader) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-[2px] font-sans text-[11px] font-semibold border bg-signal-pos/12 text-signal-pos border-signal-pos/30">
        Atlas Leader
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-[2px] font-sans text-[11px] font-medium border bg-paper-deep text-ink-tertiary border-paper-rule">
      Watch List
    </span>
  )
}

// ---------------------------------------------------------------------------
// Individual conviction row
// ---------------------------------------------------------------------------

function ConvRow({ row, tabKey }: { row: ConvictionCallRow; tabKey: TabKey }) {
  const excess = row.predicted_excess
  const isPos = excess != null && excess.startsWith('+')
  const isNeg = excess != null && excess.startsWith('-')

  // Per [[everything-clickable]] memory — every symbol routes to its deep-dive
  // page. Stocks/ETFs use the symbol directly; funds aren't routable from this
  // row yet because mstar_id isn't returned by getTopConvictionCalls(). Falls
  // back to clickable-but-no-href styling for funds — TODO: surface mstar_id
  // in the landing query.
  const href = tabKey === 'stocks' ? `/stocks/${encodeURIComponent(row.symbol)}`
             : tabKey === 'etfs'   ? `/etfs/${encodeURIComponent(row.symbol)}`
             : null

  const rowClass = "grid items-center gap-4 px-3 py-2 rounded-[2px] hover:bg-paper-deep transition-colors cursor-pointer"
  const rowStyle = { gridTemplateColumns: '130px 1fr 110px 1fr 80px 72px' }

  const inner = (
    <>
      {/* Symbol + NEW badge */}
      <div className="font-mono text-[13px] font-medium text-ink-primary flex items-center gap-1.5">
        {row.symbol}
        {row.is_new && (
          <span className="inline-block px-1 py-px text-[9px] font-bold uppercase tracking-[0.14em] rounded-[2px] bg-accent text-paper">
            NEW
          </span>
        )}
      </div>

      {/* Name + sector */}
      <div className="font-sans text-[12px] text-ink-tertiary leading-tight">
        {row.company_name && (
          <span className="text-ink-secondary font-medium">{row.company_name}</span>
        )}
        {row.sector && (
          <span className="ml-1">
            · {row.sector}
            {row.cap_tier && <span> · {row.cap_tier}-cap</span>}
          </span>
        )}
      </div>

      {/* Cell label */}
      <div className="font-sans text-[12px] text-ink-tertiary truncate">
        {row.cell_label}
      </div>

      {/* Confidence bar (stocks/ETFs) or quality badge column (funds) */}
      {row.is_fund ? (
        <FundQualityBadge is_atlas_leader={row.is_atlas_leader} />
      ) : (
        <ConfidenceBar value={row.confidence} action={row.action} />
      )}

      {/* Action badge */}
      <ActionBadge action={row.action} />

      {/* Predicted excess */}
      <div
        className={`font-mono text-[12px] text-right ${
          isPos ? 'text-signal-pos' : isNeg ? 'text-signal-neg' : 'text-ink-tertiary'
        }`}
      >
        {excess ?? '—'}
      </div>
    </>
  )

  if (href) {
    return (
      <Link href={href} className={rowClass} style={rowStyle} role="row">
        {inner}
      </Link>
    )
  }
  return (
    <div className={rowClass} style={rowStyle} role="row">
      {inner}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyPane({ label }: { label: string }) {
  return (
    <div className="py-8 text-center">
      <p className="font-sans text-[13px] text-ink-tertiary">
        No active {label} calls at this time.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab bar
// ---------------------------------------------------------------------------

type TabConfig = {
  key: TabKey
  label: string
  count: number
  newCount: number
}

function TabBar({
  tabs,
  active,
  onSelect,
}: {
  tabs: TabConfig[]
  active: TabKey
  onSelect: (k: TabKey) => void
}) {
  return (
    <div
      className="flex border-b border-paper-rule mb-5"
      role="tablist"
      aria-label="Conviction tabs"
    >
      {tabs.map(tab => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onSelect(tab.key)}
          className={`px-4 py-2.5 font-sans text-[13px] font-medium relative top-px border-b-2 transition-colors ${
            active === tab.key
              ? 'text-ink-primary border-accent'
              : 'text-ink-tertiary border-transparent hover:text-ink-secondary'
          }`}
        >
          {tab.label}
          {tab.count > 0 && (
            <span
              className={`ml-1.5 font-mono text-[11px] ${active === tab.key ? 'text-ink-tertiary' : 'text-paper-rule'}`}
            >
              {tab.count} active{tab.newCount > 0 ? ` · ${tab.newCount} new` : ''}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Column header row — switches label for confidence column based on tab
// ---------------------------------------------------------------------------

function ColumnHeaders({ activeTab }: { activeTab: TabKey }) {
  const confidenceLabel = activeTab === 'funds' ? 'Quality' : 'Confidence'
  return (
    <div
      className="grid px-3 mb-1"
      style={{ gridTemplateColumns: '130px 1fr 110px 1fr 80px 72px' }}
    >
      <span className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">Symbol</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">Name / Sector</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">Signal</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">{confidenceLabel}</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">Action</span>
      <span className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold text-right">Expected</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function TodayConvictionTabs({ data }: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('stocks')

  // Mockup tab order: Stocks | Funds | ETFs  (01-market-regime.html:893-895)
  const tabs: TabConfig[] = [
    {
      key: 'stocks',
      label: 'Stocks',
      count: data.stocks.length,
      newCount: data.stocks_new_count,
    },
    {
      key: 'funds',
      label: 'Funds',
      count: data.funds.length,
      newCount: data.funds_new_count,
    },
    {
      key: 'etfs',
      label: 'ETFs',
      count: data.etfs.length,
      newCount: data.etfs_new_count,
    },
  ]

  const rows: ConvictionCallRow[] =
    activeTab === 'stocks' ? data.stocks :
    activeTab === 'funds'  ? data.funds  :
    data.etfs

  return (
    <section
      className="py-10 border-b border-paper-rule"
      aria-label="Today's conviction"
    >
      <div className="max-w-[1400px] mx-auto px-8">
        {/* Section header */}
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h2
              className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary"
            >
              Today&apos;s conviction
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1">
              Strongest combined signal agreement across stocks, funds, and ETFs.{' '}
              <span className="inline-block px-1 py-px text-[9px] font-bold uppercase tracking-[0.14em] rounded-[2px] bg-accent text-paper align-middle">
                NEW
              </span>{' '}
              = signal fired at today&apos;s close.
            </p>
          </div>
        </div>

        {/* Tabs */}
        <TabBar tabs={tabs} active={activeTab} onSelect={setActiveTab} />

        {/* Pane */}
        <div role="tabpanel" aria-label={`${activeTab} conviction calls`}>
          {/* Column headers */}
          {rows.length > 0 && <ColumnHeaders activeTab={activeTab} />}

          {/* Rows */}
          <div className="flex flex-col gap-0.5" role="list" aria-label={`${activeTab} calls`}>
            {rows.length === 0 ? (
              <EmptyPane label={activeTab} />
            ) : (
              rows.map((row, i) => (
                <ConvRow key={`${row.symbol}-${i}`} row={row} tabKey={activeTab} />
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
