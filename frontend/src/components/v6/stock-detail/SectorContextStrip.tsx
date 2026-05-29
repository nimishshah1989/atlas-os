// Sector context strip: shows where the parent stock fits in its sector right now.
// One horizontal row of 4 cells: sector state, sector RS rank, breadth, this stock's rank in sector.
// Pure server component.

import Link from 'next/link'

interface SectorContextStripProps {
  sectorName: string | null
  /** sector_state from atlas_sector_states_daily — 'Overweight'|'Neutral'|'Avoid' */
  sectorState: string | null
  /** sector breadth (% of sector constituents above 200DMA, or similar). 0..1 */
  breadth: number | null
  /** rank of the sector among all sectors by 3M RS */
  sectorRank: number | null
  totalSectors: number | null
  /** rank of THIS stock within the sector, by 3M RS or composite */
  stockRankInSector: number | null
  sectorSize: number | null
}

function sectorStateColor(state: string | null): string {
  if (state === 'Overweight') return 'text-signal-pos'
  if (state === 'Avoid') return 'text-signal-neg'
  return 'text-ink-3'
}

interface CellProps {
  label: string
  value: string
  valueClass?: string
  sublabel?: string
}

function Cell({ label, value, valueClass = 'text-ink', sublabel }: CellProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="font-mono text-[9px] uppercase tracking-wider text-ink-3">{label}</p>
      <p className={`font-mono text-[14px] font-semibold leading-none ${valueClass}`}>{value}</p>
      {sublabel && <p className="font-sans text-[10px] text-ink-4 leading-none mt-0.5">{sublabel}</p>}
    </div>
  )
}

export function SectorContextStrip({
  sectorName,
  sectorState,
  breadth,
  sectorRank,
  totalSectors,
  stockRankInSector,
  sectorSize,
}: SectorContextStripProps) {
  if (!sectorName) return null

  return (
    <section className="px-6 py-4 border-b border-paper-rule bg-paper">
      <div className="flex items-center justify-between mb-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          Sector Context — <Link href={`/sectors/${encodeURIComponent(sectorName)}`} className="text-accent hover:underline">{sectorName}</Link>
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <Cell
          label="Sector State"
          value={sectorState ?? '—'}
          valueClass={sectorStateColor(sectorState)}
          sublabel="from atlas_sector_states_daily"
        />
        <Cell
          label="Breadth"
          value={breadth != null ? `${Math.round(breadth * 100)}%` : '—'}
          valueClass={breadth != null && breadth >= 0.5 ? 'text-signal-pos' : 'text-ink-3'}
          sublabel="% above 200DMA"
        />
        <Cell
          label="Sector Rank"
          value={sectorRank != null && totalSectors != null ? `${sectorRank}/${totalSectors}` : '—'}
          valueClass="text-ink"
          sublabel="by 3M RS"
        />
        <Cell
          label="Stock Rank in Sector"
          value={stockRankInSector != null && sectorSize != null ? `${stockRankInSector}/${sectorSize}` : '—'}
          valueClass="text-teal"
          sublabel="by 3M RS"
        />
      </div>
    </section>
  )
}
