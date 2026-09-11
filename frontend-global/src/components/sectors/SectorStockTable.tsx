'use client'
// SectorStockTable — the S&P 500 companies filed under this sector, ranked against each other.
//
// The FM: "when you double-click on sectors, you have both stocks and ETFs coming into play."
// The funds are the drill-down above this; these are the companies.
//
// TWO NUMBERS, TWO POPULATIONS, AND THE HEADERS SAY WHICH. `Rank` is cut over this SECTOR — the
// answer to "which name in Energy". `Decile` is the company's standing in its own CAP COHORT, the
// same cut /sp500 shows, carried across rather than re-cut here. Re-cutting it inside the sector
// would rank Energy's mega-caps against Energy's mega-caps and print the result under a word that
// already means something else.
import Link from 'next/link'
import { AddToDraft } from '@/components/portfolios/AddToDraft'
import { useState } from 'react'
import { DecileChip } from '@/components/ui/DecileChip'
import { InfoTip } from '@/components/ui/InfoTip'
import { formatDecimal, formatPct, formatUsdCompact } from '@/lib/format'
import { rsTint } from '@/lib/scores'
import type { SectorStock } from '@/lib/sectors'

const L = { textAlign: 'left' } as const
const R = { textAlign: 'right' } as const
const NUM = 'px-2 py-1.5 text-right font-num text-[12.5px] tabular-nums'

/** How many rows before the table folds. A sector holds up to ~70 S&P names and the reader came
 *  for the top of it; the rest is one click away rather than a page of scrolling. */
const FOLD = 12

export function SectorStockTable({ rows }: { rows: readonly SectorStock[] }) {
  const [all, setAll] = useState(false)
  if (rows.length === 0) {
    return (
      <p className="panel px-4 py-4 text-[13px] text-ink-2">
        No S&P 500 member is filed under this sector — `ingest_index_membership.py` writes
        `sector_gics` from the Select Sector SPDR holdings, and it has not reached this sector yet.
      </p>
    )
  }
  const shown = all ? rows : rows.slice(0, FOLD)

  return (
    <div className="panel overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse">
          <thead>
            <tr>
              <th style={{ ...L, paddingLeft: 8 }}>Company</th>
              <th style={R}>
                Rank{' '}
                <InfoTip title="Within this sector">
                  Cut over this sector&apos;s scored S&amp;P 500 members, not over the index — the
                  answer to &ldquo;which name here&rdquo;.
                </InfoTip>
              </th>
              <th style={R}>Score</th>
              <th style={R}>
                Decile{' '}
                <InfoTip title="Within its cap cohort">
                  The company&apos;s standing among index members of its own size, which is the cut
                  the score page shows. A different population from the rank beside it.
                </InfoTip>
              </th>
              <th style={R}>vs S&P 3m</th>
              <th style={R}>vs S&P 12m</th>
              <th style={R}>200d</th>
              <th style={R}>ADV$</th>
              <th style={{ ...R, textAlign: 'center' }} title="Add to a draft basket">+</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.symbol} className="border-t border-hair hover:bg-raised">
                <td className="py-1.5 pl-2 pr-2">
                  <span className="flex items-baseline gap-2">
                    <Link href={`/sp500/${encodeURIComponent(r.symbol)}`} className="dt-symbol shrink-0 hover:underline">
                      {r.symbol}
                    </Link>
                    <span className="truncate text-[12.5px] text-ink-2" title={r.name ?? undefined}>
                      {r.name ?? '—'}
                    </span>
                  </span>
                </td>
                <td className={`${NUM} text-ink-2`}>
                  {r.rank == null ? <span className="text-ink-3">—</span> : `${r.rank}/${r.n_ranked}`}
                </td>
                <td className={`${NUM} font-display font-semibold text-ink`}>
                  {formatDecimal(r.composite, 0)}
                </td>
                <td className={NUM}>
                  <DecileChip decile={r.decile} />
                </td>
                <td className={NUM} style={{ background: rsTint(r.rs_3m_spy) }}>
                  {r.rs_3m_spy == null ? <span className="text-ink-3">—</span> : formatPct(r.rs_3m_spy, 1, { sign: true })}
                </td>
                <td className={NUM} style={{ background: rsTint(r.rs_12m_spy) }}>
                  {r.rs_12m_spy == null ? <span className="text-ink-3">—</span> : formatPct(r.rs_12m_spy, 1, { sign: true })}
                </td>
                <td className={NUM}>
                  {r.above_ema_200 == null ? (
                    <span className="text-ink-3" title="Fewer than 200 sessions">—</span>
                  ) : (
                    <span style={{ color: r.above_ema_200 ? 'var(--color-pos)' : 'var(--color-neg)' }}>
                      {r.above_ema_200 ? '▲' : '▼'}
                    </span>
                  )}
                </td>
                <td className={`${NUM} text-ink-2`}>{formatUsdCompact(r.adv_usd)}</td>
                <td className="px-2 py-1.5 text-center">
                  <AddToDraft kind="stock" symbol={r.symbol} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > FOLD && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="w-full border-t border-hair py-1.5 font-num text-[11px] text-ink-2 hover:bg-inset"
        >
          {all ? 'Show the top 12' : `Show all ${rows.length}`}
        </button>
      )}
    </div>
  )
}
