import Link from 'next/link'
import { ChevronRight } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'
import { StateTuple3 } from '@/lib/stock-formatters'

const THEME_STYLE: Record<string, string> = {
  Broad:     'bg-teal/10 text-teal',
  Sectoral:  'bg-signal-pos/10 text-signal-pos',
  Thematic:  'bg-signal-warn/10 text-signal-warn',
}

function ThemeBadge({ theme }: { theme: string }) {
  const style = THEME_STYLE[theme] ?? 'bg-ink-tertiary/10 text-ink-secondary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${style}`}>
      {theme}
    </span>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).replace(',', '')
}

export function ETFDeepDiveHeader({ etf }: { etf: ETFRow }) {
  return (
    <div className="sticky top-14 bg-paper border-b border-paper-rule z-30">
      <div className="px-6 py-4">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/etfs" className="hover:text-ink-secondary transition-colors">ETFs</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-ink-secondary">{etf.ticker}</span>
        </nav>

        {/* Headline row */}
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div className="flex items-end gap-3 flex-wrap">
            <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
              {etf.ticker}
            </h1>
            <span className="font-sans text-sm text-ink-secondary">{etf.etf_name ?? ''}</span>
            <ThemeBadge theme={etf.theme} />
            {etf.linked_sector && (
              <span className="font-sans text-xs text-ink-tertiary">{etf.linked_sector}</span>
            )}
            {etf.linked_index && (
              <span className="font-sans text-xs text-ink-tertiary bg-paper-rule/30 px-1.5 py-0.5 rounded">
                {etf.linked_index}
              </span>
            )}
            <StateTuple3
              rs={etf.rs_state}
              mom={etf.momentum_state}
              risk={etf.risk_state}
            />
          </div>
          <div className="flex items-center gap-5 font-sans text-xs text-ink-tertiary">
            {etf.inception_date && (
              <span>Since <span className="text-ink-secondary">{formatDate(etf.inception_date)}</span></span>
            )}
            {etf.position_size_pct && (
              <span>
                Pos Size:{' '}
                <span className="font-mono font-semibold text-ink-primary">
                  {(parseFloat(etf.position_size_pct) * 100).toFixed(2)}%
                </span>
              </span>
            )}
            {etf.is_investable && (
              <span className="text-signal-pos font-semibold">● Investable</span>
            )}
            {etf.fund_house && (
              <span className="text-ink-tertiary">{etf.fund_house}</span>
            )}
            {etf.data_as_of && (
              <span className="text-ink-tertiary/60 text-[10px]">
                Data as of {formatDate(etf.data_as_of)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
