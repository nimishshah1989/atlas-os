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
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import type { ConvictionCallRow, ConvictionCallsResult } from '@/lib/queries/v6/landing'

// Column-header tooltips. Each tooltip's translation answers the user's
// actual question (what does this column tell me / why does it look uniform).
const COL_TOOLTIPS = {
  confidence: {
    content: 'Cell hit rate — same for every stock in the same cap × tenure cell.',
    translation: 'Not a per-stock score. Varies across cells; identical within one.',
  },
  expected: {
    content: 'Predicted excess return over the call\'s tenure horizon.',
  },
  days: {
    content: 'Trading days since this call first fired.',
  },
} as const

type TabKey = 'stocks' | 'funds' | 'etfs'

type Props = {
  data: ConvictionCallsResult
}

// ---------------------------------------------------------------------------
// Confidence bar — for stocks and ETFs only (signal conviction probability)
// ---------------------------------------------------------------------------

// Compact confidence indicator — short bar (32px) + numeric pct.
// Replaces the 1fr-wide full bar that ate the table. User feedback 2026-05-29:
// "confidence should not be shown like such a big bar".
function ConfidenceBar({ value, action }: { value: number; action: string }) {
  const fillClass =
    action === 'NEGATIVE' ? 'bg-signal-neg' :
    action === 'NEUTRAL'  ? 'bg-signal-warn' :
    'bg-signal-pos'

  const pct = Math.min(100, Math.max(0, Math.round(value * 100)))

  return (
    <div
      className="flex items-center gap-1.5"
      role="meter"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Confidence: ${pct}%`}
    >
      <div className="h-1 w-8 rounded-[1px] overflow-hidden bg-paper-deep flex-shrink-0">
        <div
          className={`h-full rounded-[1px] transition-all ${fillClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[11px] text-ink-secondary tabular-nums">{pct}%</span>
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
  // ret_since_entry replaces the old bare "Days" column — shows % move + days held stacked.
  const rowStyle = { gridTemplateColumns: '120px 1fr 110px 90px 72px 80px 72px' }

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

      {/* Predicted excess */}
      <div
        className={`font-mono text-[12px] text-right ${
          isPos ? 'text-signal-pos' : isNeg ? 'text-signal-neg' : 'text-ink-tertiary'
        }`}
      >
        {excess ?? '—'}
      </div>

      {/* Action badge */}
      <ActionBadge action={row.action} />

      {/* Return since entry + days held stacked */}
      <div className="text-right tabular-nums flex flex-col items-end gap-px">
        {row.ret_since_entry != null ? (
          <span
            className={`font-mono text-[12px] font-semibold ${
              row.ret_since_entry > 0 ? 'text-signal-pos' : row.ret_since_entry < 0 ? 'text-signal-neg' : 'text-ink-tertiary'
            }`}
          >
            {row.ret_since_entry > 0 ? '+' : ''}{(row.ret_since_entry * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="font-mono text-[12px] text-ink-tertiary">—</span>
        )}
        {row.days_held != null && (
          <span className="font-mono text-[9px] text-ink-tertiary">d{row.days_held}</span>
        )}
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
  const headerClass = "font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold flex items-center gap-1"
  return (
    <div
      className="grid px-3 mb-1 gap-4"
      style={{ gridTemplateColumns: '120px 1fr 110px 90px 72px 80px 72px' }}
    >
      <span className={headerClass}>Symbol</span>
      <span className={headerClass}>Name / Sector</span>
      <span className={headerClass}>Signal</span>
      <span className={headerClass}>
        {confidenceLabel}
        {activeTab !== 'funds' && (
          <InfoTooltip content={COL_TOOLTIPS.confidence.content} translation={COL_TOOLTIPS.confidence.translation} />
        )}
      </span>
      <span className={`${headerClass} justify-end`}>
        Expected
        <InfoTooltip content={COL_TOOLTIPS.expected.content} />
      </span>
      <span className={headerClass}>Action</span>
      <span className={`${headerClass} justify-end`}>
        Since
        <InfoTooltip content={COL_TOOLTIPS.days.content} />
      </span>
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

  // Data-quality flags: surfaced as a single small banner above the table so
  // the user doesn't read uniform-looking columns as a UI bug.
  const everyExpectedNull = rows.length > 0 && rows.every(r => r.predicted_excess == null)
  const distinctDays = new Set(
    rows.map(r => r.days_held).filter((d): d is number => d != null)
  )
  const everyDaysSame = distinctDays.size === 1 && rows.length > 1
  const everyConfSame = rows.length > 1 && new Set(rows.map(r => r.confidence)).size === 1

  return (
    <section
      className="py-10 border-b border-paper-rule"
      aria-label="Top conviction"
    >
      <div className="max-w-[1400px] mx-auto px-8">
        {/* Section header */}
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h2
              className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary"
            >
              Top conviction
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1 max-w-[820px]">
              Highest-confidence active calls across stocks, funds, and ETFs.{' '}
              <span className="inline-block px-1 py-px text-[9px] font-bold uppercase tracking-[0.14em] rounded-[2px] bg-accent text-paper align-middle">
                NEW
              </span>{' '}
              = signal fired at today&apos;s close. Confidence is a cell-level prior (same for every stock in a given cap × tenure cell); Expected is the per-stock predicted excess return. Hover any column header for details.
            </p>
          </div>
        </div>

        {/* Tabs */}
        <TabBar tabs={tabs} active={activeTab} onSelect={setActiveTab} />

        {/* Data-quality banner — surfaces backend gaps honestly instead of
            letting the user mistake uniform columns for a UI bug. */}
        {activeTab !== 'funds' && (everyExpectedNull || everyDaysSame || everyConfSame) && (
          <div
            role="note"
            className="mb-3 px-3 py-2 rounded-[2px] border border-signal-warn/30 bg-signal-warn/8 text-[12px] text-ink-secondary leading-relaxed"
          >
            <span className="font-medium text-signal-warn">Data quality:</span>{' '}
            {everyExpectedNull && (
              <span>Predicted excess is unwritten in the live set — column shows em-dashes. </span>
            )}
            {everyDaysSame && (
              <span>All visible calls share entry_date {Array.from(distinctDays)[0] != null ? `(d${Array.from(distinctDays)[0]})` : ''} — nightly recompute may be re-stamping signal_call_ids. </span>
            )}
            {everyConfSame && !everyDaysSame && (
              <span>Confidence clusters at one value because the top-N filter selects within the same cell. Switch tabs or scroll into lower-tier cells for spread. </span>
            )}
          </div>
        )}

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
