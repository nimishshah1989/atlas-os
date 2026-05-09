import Link from 'next/link'

const SECTOR_COLORS: Record<string, { bg: string; text: string }> = {
  'Energy':           { bg: 'bg-teal/15',            text: 'text-teal' },
  'Financials':       { bg: 'bg-blue-500/15',         text: 'text-blue-600' },
  'IT':               { bg: 'bg-violet-500/15',        text: 'text-violet-600' },
  'Healthcare':       { bg: 'bg-emerald-500/15',       text: 'text-emerald-600' },
  'Consumer Disc':    { bg: 'bg-orange-500/15',        text: 'text-orange-600' },
  'Consumer Staples': { bg: 'bg-yellow-500/15',        text: 'text-yellow-700' },
  'Industrials':      { bg: 'bg-slate-500/15',         text: 'text-slate-600' },
  'Materials':        { bg: 'bg-amber-500/15',         text: 'text-amber-700' },
  'Utilities':        { bg: 'bg-cyan-500/15',          text: 'text-cyan-700' },
  'Real Estate':      { bg: 'bg-rose-500/15',          text: 'text-rose-600' },
  'Telecom':          { bg: 'bg-purple-500/15',        text: 'text-purple-600' },
  'Auto':             { bg: 'bg-lime-500/15',           text: 'text-lime-700' },
}
// Fallback for unmapped sector strings.
// IMPORTANT: verify keys against actual DB values:
//   SELECT DISTINCT sector FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL ORDER BY sector;
const DEFAULT_SECTOR_COLOR = { bg: 'bg-paper-rule/30', text: 'text-ink-secondary' }

export function SectorBadge({ sector }: { sector: string }) {
  const colors = SECTOR_COLORS[sector] ?? DEFAULT_SECTOR_COLOR
  return (
    <Link
      href={`/sectors/${encodeURIComponent(sector)}`}
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${colors.bg} ${colors.text} hover:opacity-80 transition-opacity`}
    >
      {sector}
    </Link>
  )
}
