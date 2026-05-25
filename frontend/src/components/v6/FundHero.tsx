'use client'

// frontend/src/components/v6/FundHero.tsx
//
// Hero panel for the v6 fund detail page.
// Layers: grade chip + fund name + AMC pill + PortfolioBadge (expanded, when held) +
//         SwitchProposalsBanner (when source_code matches this fund's code) +
//         manager tenure + AUM + expense (TER) + exit load pill + thesis bullets
//
// All Decimal columns arrive as strings; toNumber() converts at the boundary.
// Silent absence rules:
//   - PortfolioBadge: hidden when holdingState === null (FM-critic §1.7)
//   - SwitchProposalsBanner: hidden when switchProposals.length === 0

import { GradeChip } from './GradeChip'
import { PortfolioBadge } from './PortfolioBadge'
import { SwitchProposalsBanner } from './SwitchProposalsBanner'
import { toNumber } from '@/lib/v6/decimal'
import type { FundDetail } from '@/lib/queries/v6/funds'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { SwitchProposal } from '@/lib/queries/v6/switch_proposals'
import type { Grade } from './GradeChip'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FundHeroProps {
  fund: FundDetail
  holdingState: HoldingState | null
  /** All switch proposals — FundHero shows only those matching this fund's code */
  switchProposals: SwitchProposal[]
  className?: string
}

// ---------------------------------------------------------------------------
// Grade derivation — map composite score to Atlas grade chip
// ---------------------------------------------------------------------------

function deriveGrade(fund: FundDetail): Grade {
  if (fund.is_avoid) return 'B'
  if (fund.confidence_low) return 'BBB'
  const score = toNumber(fund.composite_score)
  if (score === null) return 'BBB'
  if (score >= 85) return 'AAA'
  if (score >= 70) return 'AA'
  if (score >= 55) return 'A'
  if (score >= 40) return 'BBB'
  if (score >= 25) return 'BB'
  return 'B'
}

// ---------------------------------------------------------------------------
// Metric tile helper
// ---------------------------------------------------------------------------

function MetricTile({
  label,
  value,
  valueClass = 'text-ink-primary',
  hint,
}: {
  label: string
  value: string
  valueClass?: string
  hint?: string
}) {
  return (
    <div className="flex flex-col gap-0.5" title={hint}>
      <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</span>
      <span className={`font-mono text-sm font-semibold tabular-nums ${valueClass}`}>{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTenure(yearsStr: string | null): string {
  const n = toNumber(yearsStr)
  if (n === null) return '—'
  if (n < 1) return '< 1 yr'
  return `${Math.floor(n)} yr${Math.floor(n) === 1 ? '' : 's'}`
}

function formatAum(aumCrStr: string | null): string {
  const n = toNumber(aumCrStr)
  if (n === null) return '—'
  if (n >= 1000) {
    return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`
  }
  return `₹${n.toFixed(0)} Cr`
}

function formatTer(terStr: string | null): string {
  const n = toNumber(terStr)
  if (n === null) return '—'
  return `${n.toFixed(2)}%`
}

function formatRet(v: number | null): { text: string; cls: string } {
  if (v === null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  const sign = pct >= 0 ? '+' : ''
  const cls = pct >= 0 ? 'text-signal-pos' : 'text-signal-neg'
  return { text: `${sign}${pct.toFixed(1)}%`, cls }
}

function parseThesisBullets(eli5: string | null): string[] {
  if (!eli5) return []
  // ELI5 is plain text. Split on newline or ". " to extract bullets.
  const lines = eli5.split(/\n|(?<=\.)\s+/).map((s) => s.trim()).filter(Boolean)
  return lines.slice(0, 5)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FundHero({
  fund,
  holdingState,
  switchProposals,
  className = '',
}: FundHeroProps) {
  const grade = deriveGrade(fund)

  // Filter switch proposals to those for this specific fund
  const fundProposals = switchProposals.filter((p) => p.source_code === fund.code)

  const bullets = parseThesisBullets(fund.eli5)

  const r1m = formatRet(fund.ret_1m)
  const r3m = formatRet(fund.ret_3m)
  const r6m = formatRet(fund.ret_6m)
  const r12m = formatRet(fund.ret_12m)

  const rankText =
    fund.rank_in_category != null && fund.category_size != null
      ? `${fund.rank_in_category} / ${fund.category_size}`
      : '—'

  return (
    <div className={`px-6 py-6 border-b border-paper-rule ${className}`}>
      {/* ── Row 1: grade + fund name + AMC pill ── */}
      <div className="flex items-start justify-between flex-wrap gap-4 mb-5">
        <div className="flex items-center gap-3 flex-wrap">
          <GradeChip grade={grade} size="md" />
          <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
            {fund.name ?? fund.code}
          </h1>
          {fund.amc && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-paper-deep text-[10px] font-sans text-ink-tertiary uppercase tracking-wide">
              {fund.amc}
            </span>
          )}
          {fund.category && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full border border-paper-rule text-[10px] font-sans text-ink-tertiary">
              {fund.category}
            </span>
          )}
          {fund.is_atlas_leader && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-signal-pos/15 text-signal-pos text-[10px] font-sans font-semibold uppercase tracking-wide">
              Atlas Leader
            </span>
          )}
          {fund.confidence_low && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-signal-warn/15 text-signal-warn text-[10px] font-sans font-semibold uppercase tracking-wide">
              Low Confidence
            </span>
          )}
        </div>

        {/* PortfolioBadge expanded — silent when null (FM-critic §1.7) */}
        <PortfolioBadge
          state={holdingState}
          variant="expanded"
          data-testid="portfolio-badge"
        />
      </div>

      {/* ── Row 2: SWITCH proposals banner ── */}
      {fundProposals.length > 0 && (
        <div className="mb-5">
          <SwitchProposalsBanner proposals={fundProposals} />
        </div>
      )}

      {/* ── Row 3: Thesis bullets ── */}
      {bullets.length > 0 && (
        <div className="mb-5">
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2 block">
            Thesis
          </span>
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

      {/* ── Row 4: Metrics strip ── */}
      <div className="flex flex-wrap gap-6 mb-5 pb-4 border-b border-paper-rule">
        <MetricTile
          label="Rank in Category"
          value={rankText}
          hint="Rank within peer category by composite score"
        />
        <MetricTile
          label="Manager Tenure"
          value={formatTenure(fund.manager_tenure_years)}
          hint="Years the current fund manager has run this fund"
        />
        <MetricTile
          label="AUM"
          value={formatAum(fund.aum_cr)}
          hint="Assets under management in ₹ crore (from sub_metrics)"
        />
        <MetricTile
          label="TER"
          value={formatTer(fund.ter_pct)}
          hint="Total expense ratio (annual %)"
        />
        {fund.fund_age_years && (
          <MetricTile
            label="Fund Age"
            value={formatTenure(fund.fund_age_years)}
            hint="Fund age since inception"
          />
        )}
      </div>

      {/* ── Row 5: Returns strip ── */}
      <div className="flex flex-wrap gap-6">
        {(
          [
            { label: '1M', ...r1m },
            { label: '3M', ...r3m },
            { label: '6M', ...r6m },
            { label: '12M', ...r12m },
          ] as Array<{ label: string; text: string; cls: string }>
        ).map(({ label, text, cls }) => (
          <div key={label} className="flex flex-col gap-0.5">
            <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</span>
            <span className={`font-mono text-sm font-semibold tabular-nums ${cls}`}>{text}</span>
          </div>
        ))}
        {fund.snapshot_date && (
          <div className="flex flex-col gap-0.5 ml-auto">
            <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">As of</span>
            <span className="font-mono text-sm text-ink-tertiary">{fund.nav_as_of ?? fund.snapshot_date}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default FundHero
