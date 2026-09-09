// src/components/portfolios/BasketCards.tsx — /portfolios as cards: one tile per active basket,
// every figure a stored row (basket_master, the latest basket_nav_daily) or a NUMERIC ratio the
// query computed over stored rows. A basket the worker has not booked yet says so.
import Link from 'next/link'
import { formatIsoDate, formatPct, formatUsd } from '@/lib/format'
import type { BasketSummary } from '@/lib/queries/baskets'

export const KIND_LABEL: Record<BasketSummary['kind'], string> = {
  etf: 'ETF basket',
  country: 'Country basket',
  stock: 'Stock basket',
}

/** Sign from the NUMERIC string: no float is asked whether a return is positive. */
export function tone(fraction: string | null): string {
  if (fraction == null) return 'text-ink-3'
  if (/^-0\.0*$/.test(fraction) || /^0(\.0*)?$/.test(fraction)) return 'text-ink-2'
  return fraction.startsWith('-') ? 'text-neg' : 'text-pos'
}

export function BasketCards({ baskets }: { baskets: BasketSummary[] }) {
  if (baskets.length === 0) {
    return (
      <p className="panel max-w-[64ch] px-5 py-4 text-body text-ink-2">
        No baskets yet. Build one — a name, a kind, capital and the weights — and it is booked at the last session close
        by the next mark, within five minutes.
      </p>
    )
  }
  return (
    <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {baskets.map((b) => (
        <li key={b.id}>
          <Link href={`/portfolios/${b.id}`} className="tile block h-full" data-basket={b.id}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-body font-medium text-ink">{b.name}</span>
              <span className="text-meta text-ink-3">{KIND_LABEL[b.kind]}</span>
            </div>
            <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-meta">
              <dt className="text-ink-3">Capital</dt>
              <dd className="num text-right text-ink">{formatUsd(b.initial_capital, 0)}</dd>
              <dt className="text-ink-3">Inception</dt>
              <dd className="num text-right text-ink">{b.inception_date ? formatIsoDate(b.inception_date) : '—'}</dd>
              <dt className="text-ink-3">NAV</dt>
              <dd className="num text-right text-ink">
                {b.nav ? (
                  <>
                    {formatUsd(b.nav)} <span className="text-ink-3">at {formatIsoDate(b.nav_date!)}</span>
                  </>
                ) : (
                  <span className="text-ink-3">not marked yet</span>
                )}
              </dd>
              <dt className="text-ink-3">Since inception</dt>
              <dd className={`num text-right ${tone(b.since_inception)}`}>{formatPct(b.since_inception, 2, { sign: true })}</dd>
              <dt className="text-ink-3">vs SPY</dt>
              <dd className={`num text-right ${tone(b.vs_spy)}`}>{formatPct(b.vs_spy, 2, { sign: true })}</dd>
            </dl>
            <p className="mt-3 text-meta text-ink-3">
              {b.n_constituents} name{b.n_constituents === 1 ? '' : 's'} · v{b.current_version}
            </p>
          </Link>
        </li>
      ))}
    </ul>
  )
}
