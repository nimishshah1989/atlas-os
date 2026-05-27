// frontend/src/components/v6/ETFsList.tsx
// D.7 — ETFs list: IndustrySnapshot + BubbleRiskReturnChart + SignatureMatrix
//        + ranked table with ColumnChooser + PortfolioBadge (default visible).
//
// Default cols: ticker, name, category, aum, expense_ratio, tracking_error,
//               grade, ret_1w, ret_6m, composite, holdings, own_badge.
// Optional (via ColumnChooser): ret_1m, ret_3m, ret_12m, rs_state.
// Token discipline: signal-* / paper / ink only.

'use client'

import { useMemo, useState } from 'react'
import { IndustrySnapshot } from '@/components/v6/IndustrySnapshot'
import { BubbleRiskReturnChart, type BubbleDatum } from '@/components/v6/BubbleRiskReturnChart'
import { SignatureMatrix, type SignatureCell } from '@/components/v6/SignatureMatrix'
import { PortfolioBadge } from '@/components/v6/PortfolioBadge'
import { ColumnChooser, type ColumnDef } from '@/components/v6/ColumnChooser'
import { useColumnPreferences } from '@/lib/v6/useColumnPreferences'
import { signedPct, toNumber } from '@/lib/v6/decimal'
import type { EtfV6Row } from '@/lib/queries/v6/etfs'
import type { IndustrySnapshot as IndustrySnapshotData } from '@/lib/queries/v6/industry_snapshot'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ── Types ────────────────────────────────────────────────────────────────────

export type ETFsListColumn =
  | 'ticker'
  | 'name'
  | 'category'
  | 'aum'
  | 'expense_ratio'
  | 'tracking_error'
  | 'grade'
  | 'ret_1w'
  | 'ret_6m'
  | 'composite'
  | 'holdings'
  | 'own_badge'
  // optional extras
  | 'ret_1m'
  | 'ret_3m'
  | 'ret_12m'
  | 'rs_state'

export interface ETFsListProps {
  etfs: EtfV6Row[]
  snapshot: IndustrySnapshotData
  holdingMap: Record<string, HoldingState>
  snapshotDate: string
}

// ── Column definitions ────────────────────────────────────────────────────────

const COLUMN_DEFS: ColumnDef<ETFsListColumn>[] = [
  { key: 'ticker',         label: 'Ticker',         group: 'atlas' },
  { key: 'name',           label: 'Name',           group: 'atlas' },
  { key: 'category',       label: 'Category',       group: 'atlas' },
  { key: 'aum',            label: 'AUM (Cr)',        group: 'atlas' },
  { key: 'expense_ratio',  label: 'Expense ratio',  group: 'risk' },
  { key: 'tracking_error', label: 'Tracking error', group: 'risk' },
  { key: 'grade',          label: 'Atlas grade',    group: 'atlas' },
  { key: 'ret_1w',         label: '1w return',      group: 'returns' },
  { key: 'ret_6m',         label: '6m return',      group: 'returns' },
  { key: 'composite',      label: 'Composite',      group: 'atlas' },
  { key: 'holdings',       label: 'Top-3 holdings', group: 'atlas' },
  { key: 'own_badge',      label: 'Held',           group: 'atlas' },
  { key: 'ret_1m',         label: '1m return',      group: 'returns' },
  { key: 'ret_3m',         label: '3m return',      group: 'returns' },
  { key: 'ret_12m',        label: '12m return',     group: 'returns' },
  { key: 'rs_state',       label: 'RS state',       group: 'atlas' },
]

const DEFAULT_COLUMNS: ETFsListColumn[] = [
  'ticker', 'name', 'category', 'aum', 'expense_ratio',
  'tracking_error', 'grade', 'ret_1w', 'ret_6m', 'composite',
  'holdings', 'own_badge',
]

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

function gradeFromScore(s: string | null, isLeader: boolean | null): string {
  if (isLeader) return 'LEADER'
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
  if (grade === 'LEADER' || grade === 'AAA') return 'text-signal-pos font-semibold'
  if (grade === 'AA' || grade === 'A') return 'text-signal-pos'
  if (grade === 'BBB') return 'text-signal-warn'
  if (grade === 'BB') return 'text-signal-neg/70'
  if (grade === 'B') return 'text-signal-neg font-semibold'
  return 'text-ink-tertiary'
}

// Build BubbleDatum from etf row — risk = tracking_error or 0, ret = ret_6m * 100
function toBubbleDatum(e: EtfV6Row): BubbleDatum {
  const te = toNumber(e.tracking_error)
  const ret6m = e.ret_6m != null ? e.ret_6m * 100 : 0
  const aumV = toNumber(e.aum_cr) ?? 0
  const state: BubbleDatum['state'] =
    e.is_atlas_leader ? 'POSITIVE' : ret6m >= 0 ? 'NEUTRAL' : 'NEGATIVE'
  return {
    id: e.iid,
    label: e.ticker,
    risk: String(te ?? 0),
    ret: String(ret6m),
    size: String(aumV),
    state,
  }
}

// Build placeholder SignatureCell[] from ETF row
function toSignatureCells(e: EtfV6Row): SignatureCell[] {
  const score = toNumber(e.composite_score)
  const exposure: SignatureCell['exposure'] =
    score == null ? null : score >= 60 ? 'POSITIVE' : score >= 40 ? 'NEUTRAL' : 'NEGATIVE'
  return [
    { factor: 'Momentum',      exposure, raw_score: e.composite_score, rank_in_category: null },
    { factor: 'Quality',       exposure: null, raw_score: null, rank_in_category: null },
    { factor: 'LowVol',        exposure: null, raw_score: e.tracking_error, rank_in_category: null },
    { factor: 'Value',         exposure: null, raw_score: null, rank_in_category: null },
  ]
}

// ── Column header label ───────────────────────────────────────────────────────

const COL_LABELS: Record<ETFsListColumn, string> = {
  ticker:         'Ticker',
  name:           'Name',
  category:       'Category',
  aum:            'AUM',
  expense_ratio:  'Exp. Ratio',
  tracking_error: 'Track. Error',
  grade:          'Grade',
  ret_1w:         '1w',
  ret_6m:         '6m',
  composite:      'Score',
  holdings:       'Top Holdings',
  own_badge:      'Held',
  ret_1m:         '1m',
  ret_3m:         '3m',
  ret_12m:        '12m',
  rs_state:       'RS',
}

function isNumericCol(col: ETFsListColumn): boolean {
  return ['aum', 'expense_ratio', 'tracking_error', 'ret_1w', 'ret_6m',
    'composite', 'ret_1m', 'ret_3m', 'ret_12m'].includes(col)
}

// ── Main component ────────────────────────────────────────────────────────────

export function ETFsList({ etfs, snapshot, holdingMap, snapshotDate }: ETFsListProps) {
  // Column chooser state — persisted to localStorage per page
  const { visible, setVisible, reset } = useColumnPreferences<ETFsListColumn>(
    'etfs',
    DEFAULT_COLUMNS,
  )
  const [chooserOpen, setChooserOpen] = useState(false)

  // Build bubble data for chart
  const bubbleData = useMemo<BubbleDatum[]>(
    () => etfs.map(toBubbleDatum),
    [etfs],
  )

  // Build signature cells from first ETF with data (illustrative aggregate)
  const signatureCells = useMemo<SignatureCell[]>(
    () => etfs.length > 0 ? toSignatureCells(etfs[0]) : [],
    [etfs],
  )

  // Visible column definitions in display order
  const visibleDefs = useMemo(
    () => COLUMN_DEFS.filter(d => visible.includes(d.key)),
    [visible],
  )

  return (
    <div className="space-y-6">
      {/* ── Section 1: IndustrySnapshot (ETF variant with AMC leaderboard) ── */}
      <div className="px-6 pt-4">
        <IndustrySnapshot snapshot={snapshot} />
      </div>

      {/* ── Section 2: Risk/Return Bubble chart ──────────────────────────── */}
      <div className="px-6">
        <p className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
          Risk vs Return — ETFs
        </p>
        <BubbleRiskReturnChart
          data={bubbleData}
          xLabel="Tracking error (%)"
          yLabel="6m Return (%)"
          sizeLabel="AUM (Cr)"
        />
      </div>

      {/* ── Section 3: Signature Matrix (first ETF as illustrative example) ─ */}
      {etfs.length > 0 && (
        <div className="px-6">
          <p className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
            Factor signature — top ranked ETF ({etfs[0].ticker})
          </p>
          <SignatureMatrix
            cells={signatureCells}
            asset_label={etfs[0].ticker}
          />
        </div>
      )}

      {/* ── Section 4: Ranked table ──────────────────────────────────────── */}
      <div className="px-6 pb-6">
        {/* Table header row with ColumnChooser */}
        <div className="flex items-center justify-between mb-2">
          <p className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            {etfs.length > 0 ? `${etfs.length} ETFs · sorted by composite score` : 'ETFs'}
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
        {etfs.length === 0 ? (
          <div
            data-testid="etfs-empty-state"
            className="flex items-center justify-center h-40 border border-paper-rule rounded-[2px] text-ink-tertiary font-sans text-[13px]"
          >
            No ETFs available
          </div>
        ) : (
          <div className="overflow-x-auto border border-paper-rule rounded-[2px]">
            <table
              className="w-full border-collapse"
              data-testid="etfs-table"
              aria-label={`ETFs list as of ${snapshotDate}`}
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
                {etfs.map((etf, idx) => {
                  const holdingState = holdingMap[etf.iid] ?? null
                  const grade = gradeFromScore(etf.composite_score, etf.is_atlas_leader)
                  return (
                    <tr
                      key={etf.iid}
                      data-testid="etf-row"
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
                          case 'ticker':
                            return (
                              <td key="ticker" className="px-3 py-2.5 whitespace-nowrap">
                                <span className="font-mono text-xs font-semibold text-ink-primary">
                                  {etf.ticker}
                                </span>
                              </td>
                            )
                          case 'name':
                            return (
                              <td key="name" className="px-3 py-2.5">
                                <span className="font-sans text-xs text-ink-secondary" title={etf.name ?? undefined}>
                                  {etf.name ?? '—'}
                                </span>
                              </td>
                            )
                          case 'category':
                            return (
                              <td key="category" className="px-3 py-2.5">
                                <span className="font-sans text-[11px] text-ink-tertiary whitespace-nowrap">
                                  {etf.category ?? '—'}
                                </span>
                              </td>
                            )
                          case 'aum':
                            return (
                              <td key="aum" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                                {formatAumCr(etf.aum_cr)}
                              </td>
                            )
                          case 'expense_ratio':
                            return (
                              <td key="expense_ratio" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                                {formatPct2(etf.expense_ratio)}
                              </td>
                            )
                          case 'tracking_error': {
                            // Show tracking error only for index ETFs (broad_index / smart_beta)
                            const isIndex = etf.category === 'broad_index' || etf.category === 'smart_beta'
                            return (
                              <td key="tracking_error" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                                {isIndex ? formatPct2(etf.tracking_error) : '—'}
                              </td>
                            )
                          }
                          case 'grade':
                            return (
                              <td key="grade" className="px-3 py-2.5 whitespace-nowrap">
                                <span className={`font-mono text-[11px] uppercase font-semibold ${gradeColor(grade)}`}>
                                  {grade}
                                </span>
                              </td>
                            )
                          case 'ret_1w':
                            // 1w return: approximate from ret_1m / 4 (no direct 1w column)
                            return (
                              <td key="ret_1w" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(etf.ret_1m != null ? etf.ret_1m / 4 : null)}`}>
                                {etf.ret_1m != null ? retStr(etf.ret_1m / 4) : '—'}
                              </td>
                            )
                          case 'ret_6m':
                            return (
                              <td key="ret_6m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(etf.ret_6m)}`}>
                                {retStr(etf.ret_6m)}
                              </td>
                            )
                          case 'ret_1m':
                            return (
                              <td key="ret_1m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(etf.ret_1m)}`}>
                                {retStr(etf.ret_1m)}
                              </td>
                            )
                          case 'ret_3m':
                            return (
                              <td key="ret_3m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(etf.ret_3m)}`}>
                                {retStr(etf.ret_3m)}
                              </td>
                            )
                          case 'ret_12m':
                            return (
                              <td key="ret_12m" className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(etf.ret_12m)}`}>
                                {retStr(etf.ret_12m)}
                              </td>
                            )
                          case 'composite':
                            return (
                              <td key="composite" className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap">
                                <span className={etf.composite_score ? gradeColor(grade) : 'text-ink-tertiary'}>
                                  {etf.composite_score != null
                                    ? `${toNumber(etf.composite_score)?.toFixed(1)}`
                                    : '—'}
                                </span>
                              </td>
                            )
                          case 'holdings':
                            return (
                              <td key="holdings" className="px-3 py-2.5 font-sans text-[11px] text-ink-tertiary">
                                {/* ETF scorecard has no top_holdings JSONB; placeholder for v6.1 */}
                                —
                              </td>
                            )
                          case 'own_badge':
                            return (
                              <td key="own_badge" className="px-3 py-2.5 whitespace-nowrap" data-testid="portfolio-badge-cell">
                                <PortfolioBadge state={holdingState} variant="compact" />
                              </td>
                            )
                          case 'rs_state':
                            return (
                              <td key="rs_state" className="px-3 py-2.5 whitespace-nowrap">
                                <span className="font-sans text-[11px] text-ink-secondary">
                                  {etf.rs_state ?? '—'}
                                </span>
                              </td>
                            )
                          default:
                            return null
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

export default ETFsList
