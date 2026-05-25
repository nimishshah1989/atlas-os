'use client'

// frontend/src/components/v6/FundsList.tsx
//
// D.5 — Funds list: IndustrySnapshot + BubbleRiskReturnChart + SignatureMatrix
//        + ranked table with ColumnChooser + PortfolioBadge (default visible).
//
// Default cols: name, category, aum, expense_ratio, ret_12m (3y CAGR proxy),
//               peer_quartile, grade, ret_1w, composite, sector_tilt, own_badge.
// Optional (via ColumnChooser): ret_1m, ret_3m, ret_6m, rank_in_category.
// Token discipline: signal-* / paper / ink only.

import { useMemo, useState } from 'react'
import { IndustrySnapshot } from '@/components/v6/IndustrySnapshot'
import { BubbleRiskReturnChart, type BubbleDatum } from '@/components/v6/BubbleRiskReturnChart'
import { SignatureMatrix, type SignatureCell } from '@/components/v6/SignatureMatrix'
import { PortfolioBadge } from '@/components/v6/PortfolioBadge'
import { ColumnChooser, type ColumnDef } from '@/components/v6/ColumnChooser'
import { useColumnPreferences } from '@/lib/v6/useColumnPreferences'
import { signedPct, toNumber } from '@/lib/v6/decimal'
import type { IndustrySnapshot as IndustrySnapshotData } from '@/lib/queries/v6/industry_snapshot'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ── Public types ──────────────────────────────────────────────────────────────

/**
 * Extended fund row type consumed by FundsList.
 * Extends the basic ScreenFund shape (from funds.ts) with additional columns
 * needed for the D.5 ranked table.
 */
export type FundRow = {
  iid: string
  code: string
  name: string | null
  category: string | null
  aum_cr: string | null          // Stringified Decimal — AUM in ₹ crore
  expense_ratio: string | null   // Stringified Decimal — expense ratio %
  composite_score: string | null // Stringified Decimal — 0..100 score
  rank_in_category: number | null
  category_size: number | null
  is_atlas_leader: boolean | null
  is_avoid: boolean | null
  ret_1m: number | null          // Fraction (0.05 = 5%)
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null         // Used as 3y CAGR proxy (v6.0)
  rs_pctile_3m: string | null    // Peer quartile proxy from RS percentile
  sector_tilt: string | null     // Top-sector tilt text if available
}

export type FundsListColumn =
  | 'name'
  | 'category'
  | 'aum'
  | 'expense_ratio'
  | 'ret_12m'
  | 'peer_quartile'
  | 'grade'
  | 'ret_1w'
  | 'composite'
  | 'sector_tilt'
  | 'own_badge'
  // optional extras
  | 'ret_1m'
  | 'ret_3m'
  | 'ret_6m'
  | 'rank_in_category'

export interface FundsListProps {
  funds: FundRow[]
  snapshot: IndustrySnapshotData
  holdingMap: Record<string, HoldingState>
  snapshotDate: string
}

// ── Column definitions ────────────────────────────────────────────────────────

const COLUMN_DEFS: ColumnDef<FundsListColumn>[] = [
  { key: 'name',             label: 'Name',              group: 'atlas' },
  { key: 'category',         label: 'Category',          group: 'atlas' },
  { key: 'aum',              label: 'AUM (Cr)',           group: 'atlas' },
  { key: 'expense_ratio',    label: 'Expense ratio',     group: 'risk' },
  { key: 'ret_12m',          label: '12m return',        group: 'returns' },
  { key: 'peer_quartile',    label: 'Peer quartile',     group: 'atlas' },
  { key: 'grade',            label: 'Atlas grade',       group: 'atlas' },
  { key: 'ret_1w',           label: '1w NAV',            group: 'returns' },
  { key: 'composite',        label: 'Composite',         group: 'atlas' },
  { key: 'sector_tilt',      label: 'Sector tilt',       group: 'atlas' },
  { key: 'own_badge',        label: 'Held',              group: 'atlas' },
  { key: 'ret_1m',           label: '1m return',         group: 'returns' },
  { key: 'ret_3m',           label: '3m return',         group: 'returns' },
  { key: 'ret_6m',           label: '6m return',         group: 'returns' },
  { key: 'rank_in_category', label: 'Cat. rank',         group: 'atlas' },
]

const DEFAULT_COLUMNS: FundsListColumn[] = [
  'name', 'category', 'aum', 'expense_ratio', 'ret_12m',
  'peer_quartile', 'grade', 'ret_1w', 'composite', 'sector_tilt', 'own_badge',
]

// ── Column header labels ──────────────────────────────────────────────────────

const COL_LABELS: Record<FundsListColumn, string> = {
  name:             'Name',
  category:         'Category',
  aum:              'AUM',
  expense_ratio:    'Exp. Ratio',
  ret_12m:          '12m',
  peer_quartile:    'Peer Q',
  grade:            'Grade',
  ret_1w:           '1w NAV',
  composite:        'Score',
  sector_tilt:      'Sector tilt',
  own_badge:        'Held',
  ret_1m:           '1m',
  ret_3m:           '3m',
  ret_6m:           '6m',
  rank_in_category: 'Cat. Rank',
}

function isNumericCol(col: FundsListColumn): boolean {
  return ['aum', 'expense_ratio', 'ret_12m', 'ret_1w', 'composite',
    'ret_1m', 'ret_3m', 'ret_6m', 'rank_in_category'].includes(col)
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function retStr(v: number | null): string {
  return signedPct(v != null ? String(v) : null)
}

function retColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  return v >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

function formatAumCr(s: string | null): string {
  if (s == null) return '—'
  const v = toNumber(s)
  if (v == null) return '—'
  return `₹${v.toFixed(0)} Cr`
}

function formatPct2(s: string | null): string {
  if (s == null) return '—'
  const v = toNumber(s)
  if (v == null) return '—'
  return `${v.toFixed(2)}%`
}

/** Derive Atlas grade from composite_score (0..100) or is_atlas_leader flag. */
function gradeFromScore(s: string | null, isLeader: boolean | null, isAvoid: boolean | null): string {
  if (isLeader) return 'AAA'
  if (isAvoid) return 'B'
  if (s == null) return '—'
  const v = toNumber(s)
  if (v == null) return '—'
  if (v >= 80) return 'AAA'
  if (v >= 70) return 'AA'
  if (v >= 60) return 'A'
  if (v >= 50) return 'BBB'
  if (v >= 40) return 'BB'
  return 'B'
}

function gradeColor(grade: string): string {
  if (grade === 'AAA') return 'text-signal-pos font-semibold'
  if (grade === 'AA' || grade === 'A') return 'text-signal-pos'
  if (grade === 'BBB') return 'text-signal-warn'
  if (grade === 'BB') return 'text-signal-neg/70'
  if (grade === 'B') return 'text-signal-neg font-semibold'
  return 'text-ink-tertiary'
}

/** Map rs_pctile_3m (0..1) to peer quartile display string. */
function peerQuartile(pctile: string | null): string {
  if (pctile == null) return '—'
  const v = toNumber(pctile)
  if (v == null) return '—'
  if (v >= 0.75) return 'Q1'
  if (v >= 0.50) return 'Q2'
  if (v >= 0.25) return 'Q3'
  return 'Q4'
}

function quartileColor(q: string): string {
  if (q === 'Q1') return 'text-signal-pos font-semibold'
  if (q === 'Q2') return 'text-signal-pos'
  if (q === 'Q3') return 'text-signal-warn'
  if (q === 'Q4') return 'text-signal-neg'
  return 'text-ink-tertiary'
}

/** Build BubbleDatum from fund row — risk proxy = annualized vol from ret_6m variance guess. */
function toBubbleDatum(f: FundRow): BubbleDatum {
  // Risk proxy: use abs(ret_6m) * 0.5 as a rough vol stand-in (v6.0).
  // v6.1: replace with 3y annualized monthly return σ when available.
  const ret6m = f.ret_6m != null ? f.ret_6m * 100 : 0
  const riskProxy = Math.abs(ret6m) * 0.4 + 2
  const aumV = toNumber(f.aum_cr) ?? 0
  const state: BubbleDatum['state'] =
    f.is_atlas_leader ? 'POSITIVE'
    : f.is_avoid ? 'NEGATIVE'
    : ret6m >= 0 ? 'NEUTRAL' : 'NEGATIVE'
  return {
    id: f.iid,
    label: f.name ?? f.code,
    risk: String(riskProxy.toFixed(2)),
    ret: String(ret6m.toFixed(4)),
    size: String(aumV),
    state,
  }
}

/** Build placeholder SignatureCell[] from fund row. */
function toSignatureCells(f: FundRow): SignatureCell[] {
  const score = toNumber(f.composite_score)
  const exposure: SignatureCell['exposure'] =
    score == null ? null : score >= 60 ? 'POSITIVE' : score >= 40 ? 'NEUTRAL' : 'NEGATIVE'
  return [
    { factor: 'Momentum', exposure, raw_score: f.composite_score, rank_in_category: f.rank_in_category },
    { factor: 'Quality',  exposure: null, raw_score: null, rank_in_category: null },
    { factor: 'Value',    exposure: null, raw_score: null, rank_in_category: null },
    { factor: 'LowVol',   exposure: null, raw_score: null, rank_in_category: null },
  ]
}

// ── Main component ────────────────────────────────────────────────────────────

export function FundsList({ funds, snapshot, holdingMap, snapshotDate }: FundsListProps) {
  const { visible, setVisible, reset } = useColumnPreferences<FundsListColumn>(
    'funds',
    DEFAULT_COLUMNS,
  )
  const [chooserOpen, setChooserOpen] = useState(false)

  const bubbleData = useMemo<BubbleDatum[]>(
    () => funds.map(toBubbleDatum),
    [funds],
  )

  // Use first fund with data for signature illustration.
  const signatureCells = useMemo<SignatureCell[]>(
    () => funds.length > 0 ? toSignatureCells(funds[0]) : [],
    [funds],
  )

  const visibleDefs = useMemo(
    () => COLUMN_DEFS.filter(d => visible.includes(d.key)),
    [visible],
  )

  return (
    <div className="space-y-6">
      {/* ── Section 1: IndustrySnapshot (funds variant with AMC leaderboard) ── */}
      <div className="px-6 pt-4">
        <IndustrySnapshot snapshot={snapshot} />
      </div>

      {/* ── Section 2: Risk/Return Bubble chart ──────────────────────────── */}
      <div className="px-6">
        <p className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
          Risk vs Return — Funds (6m return; AUM bubble size)
        </p>
        <BubbleRiskReturnChart
          data={bubbleData}
          xLabel="Risk proxy (%)"
          yLabel="6m Return (%)"
          sizeLabel="AUM (Cr)"
        />
      </div>

      {/* ── Section 3: Signature Matrix ──────────────────────────────────── */}
      {funds.length > 0 && (
        <div className="px-6">
          <p className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
            Factor signature — top ranked fund ({funds[0].name ?? funds[0].code})
          </p>
          <SignatureMatrix
            cells={signatureCells}
            asset_label={funds[0].name ?? funds[0].code}
          />
        </div>
      )}

      {/* ── Section 4: Ranked table ──────────────────────────────────────── */}
      <div className="px-6 pb-6">
        {/* Table header row with ColumnChooser */}
        <div className="flex items-center justify-between mb-2">
          <p className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            {funds.length > 0
              ? `${funds.length} funds · sorted by composite score`
              : 'Funds'}
          </p>
          <ColumnChooser
            columns={COLUMN_DEFS}
            visible={visible}
            onVisibleChange={setVisible}
            onReset={reset}
            open={chooserOpen}
            onOpenChange={setChooserOpen}
          />
        </div>

        {/* Empty state */}
        {funds.length === 0 ? (
          <div
            data-testid="funds-empty-state"
            className="flex items-center justify-center h-40 border border-paper-rule rounded-[2px] text-ink-tertiary font-sans text-[13px]"
          >
            No funds available
          </div>
        ) : (
          <div className="overflow-x-auto border border-paper-rule rounded-[2px]">
            <table
              className="w-full border-collapse"
              data-testid="funds-table"
              aria-label={`Funds list as of ${snapshotDate}`}
            >
              <thead>
                <tr className="border-b border-paper-rule bg-paper">
                  <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left w-6">
                    #
                  </th>
                  {visibleDefs.map(col => (
                    <th
                      key={col.key}
                      className={[
                        'px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap',
                        isNumericCol(col.key) ? 'text-right' : 'text-left',
                      ].join(' ')}
                    >
                      {COL_LABELS[col.key]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {funds.map((fund, idx) => {
                  const holdingState = holdingMap[fund.iid] ?? null
                  const grade = gradeFromScore(
                    fund.composite_score, fund.is_atlas_leader, fund.is_avoid,
                  )
                  const pq = peerQuartile(fund.rs_pctile_3m)
                  return (
                    <tr
                      key={fund.iid}
                      data-testid="fund-row"
                      className={[
                        'border-b border-paper-rule hover:bg-paper-rule/20 transition-colors',
                        idx % 2 === 0 ? '' : 'bg-paper-rule/5',
                      ].join(' ')}
                    >
                      {/* Rank */}
                      <td className="px-3 py-2.5 font-mono text-[11px] text-ink-tertiary tabular-nums">
                        {idx + 1}
                      </td>

                      {visibleDefs.map(col => {
                        switch (col.key) {
                          case 'name':
                            return (
                              <td key="name" className="px-3 py-2.5 min-w-[180px]">
                                <span
                                  className="font-sans text-xs text-ink-primary font-medium leading-snug"
                                  title={fund.name ?? undefined}
                                >
                                  {fund.name ?? fund.code}
                                </span>
                              </td>
                            )
                          case 'category':
                            return (
                              <td key="category" className="px-3 py-2.5">
                                <span className="font-sans text-[11px] text-ink-tertiary whitespace-nowrap">
                                  {fund.category ?? '—'}
                                </span>
                              </td>
                            )
                          case 'aum':
                            return (
                              <td key="aum" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                                {formatAumCr(fund.aum_cr)}
                              </td>
                            )
                          case 'expense_ratio':
                            return (
                              <td key="expense_ratio" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                                {formatPct2(fund.expense_ratio)}
                              </td>
                            )
                          case 'ret_12m':
                            return (
                              <td key="ret_12m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(fund.ret_12m)}`}>
                                {retStr(fund.ret_12m)}
                              </td>
                            )
                          case 'peer_quartile':
                            return (
                              <td key="peer_quartile" className="px-3 py-2.5 whitespace-nowrap">
                                <span className={`font-mono text-[11px] font-semibold ${quartileColor(pq)}`}>
                                  {pq}
                                </span>
                              </td>
                            )
                          case 'grade':
                            return (
                              <td key="grade" className="px-3 py-2.5 whitespace-nowrap">
                                <span className={`font-mono text-[11px] uppercase font-semibold ${gradeColor(grade)}`}>
                                  {grade}
                                </span>
                              </td>
                            )
                          case 'ret_1w':
                            // 1w NAV: approximate from ret_1m / 4 (no direct 1w column in v6.0)
                            return (
                              <td key="ret_1w" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(fund.ret_1m != null ? fund.ret_1m / 4 : null)}`}>
                                {fund.ret_1m != null ? retStr(fund.ret_1m / 4) : '—'}
                              </td>
                            )
                          case 'composite':
                            return (
                              <td key="composite" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap">
                                <span className={fund.composite_score ? gradeColor(grade) : 'text-ink-tertiary'}>
                                  {fund.composite_score != null
                                    ? `${toNumber(fund.composite_score)?.toFixed(1)}`
                                    : '—'}
                                </span>
                              </td>
                            )
                          case 'sector_tilt':
                            return (
                              <td key="sector_tilt" className="px-3 py-2.5">
                                <span className="font-sans text-[11px] text-ink-secondary truncate max-w-[120px] block">
                                  {fund.sector_tilt ?? '—'}
                                </span>
                              </td>
                            )
                          case 'own_badge':
                            return (
                              <td key="own_badge" className="px-3 py-2.5 whitespace-nowrap">
                                <PortfolioBadge state={holdingState} variant="compact" />
                              </td>
                            )
                          case 'ret_1m':
                            return (
                              <td key="ret_1m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(fund.ret_1m)}`}>
                                {retStr(fund.ret_1m)}
                              </td>
                            )
                          case 'ret_3m':
                            return (
                              <td key="ret_3m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(fund.ret_3m)}`}>
                                {retStr(fund.ret_3m)}
                              </td>
                            )
                          case 'ret_6m':
                            return (
                              <td key="ret_6m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(fund.ret_6m)}`}>
                                {retStr(fund.ret_6m)}
                              </td>
                            )
                          case 'rank_in_category':
                            return (
                              <td key="rank_in_category" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                                {fund.rank_in_category != null
                                  ? `${fund.rank_in_category}${fund.category_size ? `/${fund.category_size}` : ''}`
                                  : '—'}
                              </td>
                            )
                          default:
                            return <td key={col.key} className="px-3 py-2.5">—</td>
                        }
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default FundsList
