'use client'

// frontend/src/components/v6/ETFHero.tsx
//
// Hero panel for the v6 ETF detail page.
// Layers: grade chip · ticker · category pill · PortfolioBadge (expanded, silent when null)
//         · TE vs benchmark · expense ratio · AUM + flow · bid-ask spread
//         · premium-to-NAV (when applicable) · thesis bullets (eli5)
//
// All Decimal columns arrive as strings from page.tsx; toNumber() converts at boundary.
// Missing fields render "—" (never throw).

import { GradeChip } from './GradeChip'
import { PortfolioBadge } from './PortfolioBadge'
import { toNumber } from '@/lib/v6/decimal'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { Grade } from './GradeChip'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ETFHeroData {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  composite_score: string | null
  is_atlas_leader: boolean | null
  aum_cr: string | null
  expense_ratio: string | null
  /** tracking_error_252d from raw_metrics */
  tracking_error: string | null
  /** bid-ask spread % — v6.0: not in schema, renders "—" */
  bid_ask_spread: string | null
  /** premium to NAV % — v6.0: not in schema, renders "—" */
  premium_to_nav: string | null
  /** eli5 text for thesis bullets */
  eli5: string | null
  /** net flow last 30d in Cr — v6.0: may be null */
  net_flow_30d: string | null
}

export interface ETFHeroProps {
  data: ETFHeroData
  holdingState: HoldingState | null
  className?: string
}

// ---------------------------------------------------------------------------
// Grade derivation from composite_score
// ---------------------------------------------------------------------------

function deriveGrade(compositeScore: string | null, isLeader: boolean | null): Grade {
  const n = toNumber(compositeScore)
  if (n === null) return 'failed-gate'
  if (isLeader) return 'AAA'
  if (n >= 80) return 'AA'
  if (n >= 65) return 'A'
  if (n >= 50) return 'BBB'
  if (n >= 35) return 'BB'
  return 'B'
}

// ---------------------------------------------------------------------------
// Metric tile helper
// ---------------------------------------------------------------------------

function MetricTile({
  label,
  value,
  hint,
  valueClass = 'text-ink-primary',
}: {
  label: string
  value: string
  hint?: string
  valueClass?: string
}) {
  return (
    <div
      className="flex flex-col gap-0.5 min-w-[100px]"
      title={hint}
    >
      <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
        {label}
      </span>
      <span
        className={`font-mono text-sm font-semibold tabular-nums ${valueClass}`}
        data-testid={`metric-${label.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
      >
        {value}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Formatting helpers (null-safe → "—")
// ---------------------------------------------------------------------------

function fmtPct(s: string | null | undefined, decimals = 2): string {
  const n = toNumber(s ?? null)
  if (n === null) return '—'
  return `${(n * 100).toFixed(decimals)}%`
}

function fmtAum(s: string | null | undefined): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'
  if (n >= 10000) return `₹${(n / 1000).toFixed(1)}K Cr`
  if (n >= 1000) return `₹${n.toFixed(0)} Cr`
  return `₹${n.toFixed(1)} Cr`
}

function fmtFlow(s: string | null | undefined): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}₹${n.toFixed(1)} Cr`
}

function fmtFlowClass(s: string | null | undefined): string {
  const n = toNumber(s ?? null)
  if (n === null) return 'text-ink-tertiary'
  return n >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

// Tracking error: raw_metrics stores it as a raw number (e.g. 0.023 for 2.3%)
function fmtTE(s: string | null | undefined): string {
  const n = toNumber(s ?? null)
  if (n === null) return '—'
  // If value is already >1 it's already in percentage form; otherwise fraction
  const pct = n > 1 ? n : n * 100
  return `${pct.toFixed(2)}%`
}

// ---------------------------------------------------------------------------
// Thesis bullets from eli5 text
// ---------------------------------------------------------------------------

function parseBullets(eli5: string | null): string[] {
  if (!eli5) return []
  // ELI5 text may be free-form or bullet-separated by newlines/semicolons
  const lines = eli5
    .split(/[\n;]/)
    .map((l) => l.replace(/^[\s•\-\*]+/, '').trim())
    .filter((l) => l.length > 8)
  return lines.slice(0, 5)
}

// Category display name
function categoryLabel(cat: string | null): string {
  if (!cat) return 'ETF'
  const map: Record<string, string> = {
    broad_index: 'Broad Index',
    sector: 'Sector',
    thematic: 'Thematic',
    commodity: 'Commodity',
    international: 'International',
    debt: 'Debt',
    smart_beta: 'Smart Beta',
  }
  return map[cat] ?? cat
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ETFHero({ data, holdingState, className = '' }: ETFHeroProps) {
  const grade = deriveGrade(data.composite_score, data.is_atlas_leader)
  const bullets = parseBullets(data.eli5)

  return (
    <div
      className={`px-6 py-6 border-b border-paper-rule ${className}`}
      data-testid="etf-hero"
    >
      {/* Row 1: grade chip · ticker · name · category · PortfolioBadge */}
      <div className="flex items-start justify-between flex-wrap gap-4 mb-5">
        <div className="flex items-center gap-3 flex-wrap">
          <GradeChip grade={grade} size="md" />
          <h1
            className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none"
            data-testid="etf-ticker"
          >
            {data.ticker}
          </h1>
          {data.name && (
            <span className="font-sans text-sm text-ink-secondary">
              {data.name}
            </span>
          )}
          {data.category && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-paper-deep text-[10px] font-sans text-ink-tertiary uppercase tracking-wide">
              {categoryLabel(data.category)}
            </span>
          )}
          {data.is_atlas_leader && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-signal-pos/15 text-[10px] font-sans text-signal-pos uppercase tracking-wide">
              Atlas Leader
            </span>
          )}
        </div>

        {/* PortfolioBadge expanded — silent when null (FM-critic §1.3) */}
        <PortfolioBadge
          state={holdingState}
          variant="expanded"
          data-testid="portfolio-badge"
        />
      </div>

      {/* Row 2: ETF metric tiles */}
      <div
        className="flex flex-wrap gap-6 mb-5 pb-4 border-b border-paper-rule"
        data-testid="etf-metrics"
      >
        <MetricTile
          label="Tracking Error"
          value={fmtTE(data.tracking_error)}
          hint="252-day tracking error vs benchmark index"
        />
        <MetricTile
          label="Expense Ratio"
          value={fmtPct(data.expense_ratio)}
          hint="Total expense ratio (TER)"
        />
        <MetricTile
          label="AUM"
          value={fmtAum(data.aum_cr)}
          hint="Assets under management in Crore"
        />
        <MetricTile
          label="30D Flow"
          value={fmtFlow(data.net_flow_30d)}
          valueClass={fmtFlowClass(data.net_flow_30d)}
          hint="Net inflow/outflow last 30 days in Crore"
        />
        <MetricTile
          label="Bid-Ask Spread"
          value={data.bid_ask_spread != null ? fmtPct(data.bid_ask_spread) : '—'}
          hint="Exchange bid-ask spread % (available in v6.1)"
        />
        <MetricTile
          label="Premium to NAV"
          value={data.premium_to_nav != null ? fmtPct(data.premium_to_nav) : '—'}
          hint="ETF price premium/discount to NAV (applicable when applicable)"
        />
      </div>

      {/* Row 3: Thesis bullets from eli5 */}
      {bullets.length > 0 && (
        <div data-testid="etf-thesis">
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
            Why this ETF
          </div>
          <ul className="space-y-1">
            {bullets.map((b, i) => (
              <li
                key={i}
                className="font-sans text-sm text-ink-secondary leading-relaxed flex items-start gap-2"
              >
                <span className="text-ink-tertiary mt-0.5 shrink-0">·</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default ETFHero
