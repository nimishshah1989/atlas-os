// frontend/src/app/v6/sectors/[name]/page.tsx
// v6 sector detail — constituent stocks with ConvictionTape per row.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getScreenSectors, getScreenStocks, getCellDefinitions } from '@/lib/api/v1'
import { StocksTableV6 } from '@/components/v6/StocksTableV6'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { StateBadge } from '@/components/ui/StateBadge'
import { LinkedCellById } from '@/components/v6/LinkedCell'
import type { CellRule } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

export default async function V6SectorDetailPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params
  const decoded = decodeURIComponent(name)
  const [sectorsRes, stocksRes, cellsRes] = await Promise.all([
    getScreenSectors(),
    getScreenStocks({ sector: decoded }),
    getCellDefinitions(),
  ])
  const sector = sectorsRes.data.find(s => s.sector_name === decoded)
  if (!sector) notFound()

  const cellRules = new Map<string, CellRule[]>(
    cellsRes.data.map(c => [c.cell_id, c.rules])
  )

  const r1 = sector.ret_1m != null ? `${sector.ret_1m >= 0 ? '+' : ''}${(sector.ret_1m * 100).toFixed(1)}%` : '—'
  const r3 = sector.ret_3m != null ? `${sector.ret_3m >= 0 ? '+' : ''}${(sector.ret_3m * 100).toFixed(1)}%` : '—'

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-xs text-ink-tertiary mb-1">
          <Link href="/v6/sectors" className="text-teal hover:underline">Sectors</Link>
          <span className="mx-1.5">›</span>
          {decoded}
        </div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
            {decoded}
          </h1>
          <StateBadge state={sector.sector_state} />
          <span className="font-sans text-[11px] text-ink-tertiary">
            Rank {sector.rank} · {sector.days_in_state} days in state
          </span>
        </div>
      </div>

      <DataSourceBanner source={sectorsRes.source_kind} asOf={sectorsRes.meta.data_as_of} />

      <div className="px-6 py-4 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <Metric label="Breadth (Stage 2)" value={sector.breadth_pct_stage_2 != null ? `${Math.round(sector.breadth_pct_stage_2 * 100)}%` : '—'} />
        <Metric label="Vol regime" value={sector.vol_regime} />
        <Metric label="Cross-sector RS" value={sector.rs_pct_cross_sector != null ? `${Math.round(sector.rs_pct_cross_sector * 100)}%` : '—'} />
        <Metric label="1M" value={r1} />
        <Metric label="3M" value={r3} />
      </div>

      {sector.cells_favored_today.length > 0 && (
        <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-3 flex-wrap">
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            Cells favoured today
          </span>
          {sector.cells_favored_today.map(cid => (
            <LinkedCellById key={cid} cellId={cid} className="font-mono text-xs">
              <span className="text-teal hover:underline">{cid}</span>
            </LinkedCellById>
          ))}
        </div>
      )}

      <div className="px-6 py-4">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Constituents
        </h2>
        {stocksRes.data.length === 0 ? (
          <p className="font-sans text-sm text-ink-secondary">
            No constituent stocks in the current universe. The demo dataset is curated
            to top-tier names — the live endpoint surfaces all stocks in the sector.
          </p>
        ) : (
          <StocksTableV6 stocks={stocksRes.data} cellRules={cellRules} />
        )}
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
      <div className="font-mono text-base font-semibold tabular-nums text-ink-primary leading-none mt-0.5">
        {value}
      </div>
    </div>
  )
}
