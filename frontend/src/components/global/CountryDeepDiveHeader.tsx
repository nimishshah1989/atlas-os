import Link from 'next/link'
import { ChevronRight } from 'lucide-react'
import type { CountryDetailRow } from '@/lib/queries/global'
import { rsStateColor } from '@/lib/chart-colors'

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).replace(',', '')
}

function pct(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

export function CountryDeepDiveHeader({ country }: { country: CountryDetailRow }) {
  const rsColor = country.rs_state ? rsStateColor(country.rs_state) : '#6b7280'

  return (
    <div className="sticky top-14 bg-paper border-b border-paper-rule z-30">
      <div className="px-6 py-4">
        <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/global" className="hover:text-ink-secondary transition-colors">Global Pulse</Link>
          <ChevronRight className="w-3 h-3" />
          <Link href="/global?tab=Countries" className="hover:text-ink-secondary transition-colors">Countries</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-ink-secondary">{country.country}</span>
        </nav>

        <div className="flex items-end justify-between flex-wrap gap-4">
          <div className="flex items-end gap-3 flex-wrap">
            <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
              {country.country}
            </h1>
            <span className="font-mono text-base text-ink-tertiary">{country.ticker}</span>
            <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded ${country.is_developed_market ? 'bg-teal/10 text-teal' : 'bg-amber-500/10 text-amber-600'}`}>
              {country.is_developed_market ? 'Developed Market' : 'Emerging Market'}
            </span>
            {country.rs_state && (
              <span
                className="font-sans text-[11px] font-semibold px-2 py-0.5 rounded"
                style={{ background: rsColor + '22', color: rsColor }}
              >
                {country.rs_state}
              </span>
            )}
          </div>

          <div className="flex items-center gap-5 font-sans text-xs text-ink-tertiary">
            <span>
              3M: <span className={`font-mono font-semibold ${country.ret_3m != null ? parseFloat(country.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg' : 'text-ink-secondary'}`}>
                {pct(country.ret_3m)}
              </span>
            </span>
            <span>
              1Y: <span className={`font-mono font-semibold ${country.ret_12m != null ? parseFloat(country.ret_12m) >= 0 ? 'text-signal-pos' : 'text-signal-neg' : 'text-ink-secondary'}`}>
                {pct(country.ret_12m)}
              </span>
            </span>
            <span>
              Consensus: <span className="font-mono font-semibold text-ink-primary">
                {country.rs_consensus_bullish ?? '—'}/20
              </span>
            </span>
            <span className="text-ink-tertiary">{country.region}</span>
            {country.data_as_of && (
              <span className="text-ink-tertiary/60 text-[10px]">Data as of {formatDate(country.data_as_of)}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
