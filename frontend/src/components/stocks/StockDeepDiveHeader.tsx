import Link from 'next/link'
import { ChevronRight } from 'lucide-react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { SectorBadge } from './SectorBadge'

function IndexBadge({ label }: { label: string }) {
  const encoded = encodeURIComponent(label)
  return (
    <Link
      href={`/stocks?index=${encoded}`}
      className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold bg-paper-rule/30 text-ink-secondary hover:bg-teal/10 hover:text-teal transition-colors"
    >
      {label}
    </Link>
  )
}

export function StockDeepDiveHeader({ stock }: { stock: StockRowWithSector }) {
  return (
    <div className="bg-paper border-b border-paper-rule">
      <div className="px-6 py-4">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/stocks" className="hover:text-ink-secondary transition-colors">Stocks</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-ink-secondary">{stock.symbol}</span>
        </nav>

        {/* Headline row */}
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div className="flex items-end gap-3 flex-wrap">
            <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
              {stock.symbol}
            </h1>
            <span className="font-sans text-sm text-ink-secondary">{stock.company_name}</span>
            <SectorBadge sector={stock.sector} />
            {stock.in_nifty_50 && <IndexBadge label="Nifty 50" />}
            {!stock.in_nifty_50 && stock.in_nifty_100 && <IndexBadge label="Nifty 100" />}
            {!stock.in_nifty_100 && stock.in_nifty_500 && <IndexBadge label="Nifty 500" />}
          </div>
          <div className="flex items-center gap-5 font-sans text-xs text-ink-tertiary">
            {stock.position_size_pct != null && parseFloat(stock.position_size_pct) > 0 && (
              <span>
                Pos Size:{' '}
                <span className="font-mono font-semibold text-ink-primary">
                  {(parseFloat(stock.position_size_pct) * 100).toFixed(2)}%
                </span>
              </span>
            )}
            {stock.is_investable && (
              <span className="text-signal-pos font-semibold">● Investable</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
