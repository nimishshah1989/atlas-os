'use client'
// src/components/explorer/InstrumentExplorer.tsx — the columns and facets of /etfs and /stocks over
// the rows the page loaded (one server query, virtualised here). The price-derived columns and
// the universe flag are in the row type today and join the table the moment any row carries a
// value; until then a notice says so, derived from the rows themselves, not from a flag.
import Link from 'next/link'
import { useMemo } from 'react'
import type { FacetGroup } from '@/lib/explorer'
import { expandRows, hasPrices, hasUniverse, SEC_KIND_LABEL, universeValue, words, type AssetClass, type InstrumentRow } from '@/lib/facts'
import { formatDecimal, formatIsoDate, formatPct, formatUsd } from '@/lib/format'
import type { InstrumentList } from '@/lib/queries/instruments'
import type { Column } from './DataTable'
import { Explorer } from './Explorer'

// ── facets ──────────────────────────────────────────────────────────────────

const EXCHANGE: FacetGroup<InstrumentRow> = {
  key: 'exchange', label: 'Exchange', kind: 'any', value: (r) => r.exchange ?? 'none', labels: { none: 'Not recorded' },
}
const SP500: FacetGroup<InstrumentRow> = {
  key: 'sp500', label: 'S&P 500', kind: 'one', value: (r) => (r.sp500 ? 'member' : 'other'),
  options: ['member', 'other'], labels: { member: 'Members', other: 'Not members' }, default: 'member',
}
const SECTOR: FacetGroup<InstrumentRow> = {
  key: 'sector', label: 'GICS sector', kind: 'any', value: (r) => r.sector ?? 'none', labels: { none: 'No sector' },
}
const SEC: FacetGroup<InstrumentRow> = { key: 'sec', label: 'SEC identity', kind: 'any', value: (r) => r.sec_kind, labels: SEC_KIND_LABEL }
// In universe, or the snapshot's reason for leaving the row out (below the floor, not a member, leveraged, inverse).
const UNIVERSE: FacetGroup<InstrumentRow> = {
  key: 'universe', label: 'Universe', kind: 'any', value: universeValue, labels: { in: 'In universe', excluded: 'Excluded' },
}

// ── columns ─────────────────────────────────────────────────────────────────

// For ORDERING only: a NUMERIC string compared as a double; nothing is computed from it.
const asNumber = (s: string | null) => (s == null ? null : Number(s))
const blank = (s: string | null, f: (s: string) => string) => (s == null ? '' : f(s))

const symbol = (assetClass: AssetClass): Column<InstrumentRow> => ({
  key: 'symbol', label: 'Symbol', width: 80, sortValue: (r) => r.symbol,
  render: (r) => (
    <Link href={`/${assetClass}s/${encodeURIComponent(r.symbol)}`} className="dt-symbol">
      {r.symbol}
    </Link>
  ),
})
const NAME: Column<InstrumentRow> = {
  key: 'name', label: 'Name', width: 0, sortValue: (r) => r.name,
  render: (r) => <span className="text-ink-2" title={r.name ?? undefined}>{r.name ?? ''}</span>,
}
const EXCHANGE_COL: Column<InstrumentRow> = { key: 'exchange', label: 'Exchange', width: 88, sortValue: (r) => r.exchange, render: (r) => r.exchange ?? '' }
const LISTED: Column<InstrumentRow> = {
  key: 'listed', label: 'Listed', width: 108, sortValue: (r) => r.listing_date, render: (r) => blank(r.listing_date, formatIsoDate),
}
const MEMBER: Column<InstrumentRow> = { key: 'sp500', label: 'S&P 500', width: 84, sortValue: (r) => (r.sp500 ? 1 : 0), render: (r) => (r.sp500 ? 'member' : '') }
const SECTOR_COL: Column<InstrumentRow> = { key: 'sector', label: 'GICS sector', width: 150, sortValue: (r) => r.sector, render: (r) => r.sector ?? '' }
const WEIGHT: Column<InstrumentRow> = {
  key: 'weight', label: 'SPY weight', width: 88, align: 'right', sortValue: (r) => asNumber(r.spy_weight),
  render: (r) => blank(r.spy_weight, (s) => formatPct(s, 2)),
}
const SEC_COL: Column<InstrumentRow> = { key: 'sec', label: 'SEC identity', width: 100, sortValue: (r) => r.sec_kind, render: (r) => SEC_KIND_LABEL[r.sec_kind] }
const UNIVERSE_COL: Column<InstrumentRow> = {
  key: 'universe', label: 'Universe', width: 128, sortValue: universeValue,
  render: (r) => (r.in_universe == null ? '' : words(universeValue(r))),
}

const ret = (key: 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m', label: string): Column<InstrumentRow> => ({
  key, label, width: 72, align: 'right', title: `Total return, ${label}`, sortValue: (r) => asNumber(r[key]),
  render: (r) => blank(r[key], (s) => formatPct(s, 1, { sign: true })),
})
const PRICE_COLUMNS: Column<InstrumentRow>[] = [
  { key: 'price', label: 'Price', width: 88, align: 'right', title: 'Adjusted close at EOD', sortValue: (r) => asNumber(r.price_adj), render: (r) => blank(r.price_adj, formatUsd) },
  ret('ret_1m', '1 month'), ret('ret_3m', '3 months'), ret('ret_6m', '6 months'), ret('ret_12m', '12 months'),
  { key: 'rs_3m', label: 'RS 3m', width: 76, align: 'right', title: 'Relative strength vs SPY, 3 months', sortValue: (r) => asNumber(r.rs_3m_spy), render: (r) => blank(r.rs_3m_spy, (s) => formatPct(s, 1, { sign: true })) },
  { key: 'pos_52w', label: '52w', width: 64, align: 'right', title: 'Position in the 52-week range, 0 to 100', sortValue: (r) => asNumber(r.pos_52w), render: (r) => blank(r.pos_52w, (s) => formatDecimal(s, 0)) },
  { key: 'adv', label: 'ADV$', width: 104, align: 'right', title: 'Median daily traded value over 60 sessions', sortValue: (r) => asNumber(r.adv_usd), render: (r) => blank(r.adv_usd, (s) => formatUsd(s, 0)) },
]

const FACT_COLUMNS: Record<AssetClass, Column<InstrumentRow>[]> = {
  etf: [symbol('etf'), NAME, EXCHANGE_COL, LISTED, SEC_COL],
  stock: [symbol('stock'), NAME, MEMBER, SECTOR_COL, WEIGHT, EXCHANGE_COL, LISTED, SEC_COL],
}
const FACT_GROUPS: Record<AssetClass, FacetGroup<InstrumentRow>[]> = { etf: [EXCHANGE, SEC], stock: [SP500, SECTOR, EXCHANGE, SEC] }

const DEFAULT_SORT = { key: 'symbol', dir: 'asc' } as const
const NOUN: Record<AssetClass, string> = { etf: 'ETFs', stock: 'stocks' }

export function InstrumentExplorer({ assetClass, list }: { assetClass: AssetClass; list: InstrumentList }) {
  const rows = useMemo(() => expandRows(list), [list])
  const priced = hasPrices(rows)
  const universe = hasUniverse(rows)
  const columns = useMemo(
    () => [...FACT_COLUMNS[assetClass], ...(universe ? [UNIVERSE_COL] : []), ...(priced ? PRICE_COLUMNS : [])],
    [assetClass, universe, priced],
  )
  const groups = useMemo(() => [...FACT_GROUPS[assetClass], ...(universe ? [UNIVERSE] : [])], [assetClass, universe])
  const session = list.eod ? formatIsoDate(list.eod) : 'any session'

  const missing: { lead: string; text: string }[] = []
  if (!priced) {
    missing.push({
      lead: 'Prices not loaded yet — facts only.',
      text: `Price, returns, relative strength, 52-week position and traded value join this table once the price spine has run; no row carries one for ${session}.`,
    })
  }
  if (!universe) {
    missing.push({
      lead: 'Universe not marked yet.',
      text: `The in-universe column and facet appear once the universe snapshot has run for ${session}: S&P 500 members above the liquidity floor, and ETFs above the floor that are neither leveraged nor inverse, each exclusion with its reason.`,
    })
  }

  return (
    <>
      {missing.length > 0 && (
        <div className="notice text-body" role="status">
          <span aria-hidden="true" className="dot bg-warn" />
          <div className="space-y-1">
            {missing.map((m) => (
              <p key={m.lead}>
                <span className="font-medium text-ink">{m.lead}</span> {m.text}
              </p>
            ))}
          </div>
        </div>
      )}
      <Explorer
        rows={rows}
        columns={columns}
        groups={groups}
        defaultSort={DEFAULT_SORT}
        rowKey={(r) => r.symbol}
        noun={NOUN[assetClass]}
        empty={`No ${NOUN[assetClass]} match these filters. Clear a facet or shorten the search.`}
      />
    </>
  )
}
