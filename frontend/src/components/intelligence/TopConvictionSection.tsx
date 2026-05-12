// SP04 Stage 3 — "Top Conviction Today" section on the /intelligence
// morning dashboard. Shows top picks across the two industry-grade tiers
// (T1 mega-cap + T3 upper mid-cap) plus T2 large-cap as baseline reference.
import Link from 'next/link'
import type { ConvictionRow } from '@/lib/queries/conviction'

type Props = {
  byTier: Record<string, ConvictionRow[]>
}

const TIER_DISPLAY: Array<{ key: string; label: string; badge: string }> = [
  {
    key: 'tier_1_megacap',
    label: 'Mega-cap',
    badge: '★ Industry-grade',
  },
  {
    key: 'tier_3_uppermid',
    label: 'Upper mid-cap',
    badge: '★ Industry-grade',
  },
  { key: 'tier_2_largecap', label: 'Large-cap', badge: 'Baseline' },
]

export function TopConvictionSection({ byTier }: Props) {
  const hasAny = TIER_DISPLAY.some((t) => (byTier[t.key]?.length ?? 0) > 0)
  if (!hasAny) {
    return (
      <section className="border border-paper-rule rounded-sm bg-white p-5 mt-6">
        <h2 className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3 pb-2 border-b border-paper-rule">
          Top Conviction Today
        </h2>
        <p className="font-sans text-xs text-ink-tertiary">
          Conviction scores have not been computed for the most recent date yet.
        </p>
      </section>
    )
  }

  return (
    <section className="border border-paper-rule rounded-sm bg-white p-5 mt-6">
      <div className="flex items-baseline justify-between mb-3 pb-2 border-b border-paper-rule">
        <h2 className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Top Conviction Today
        </h2>
        <span className="font-sans text-[10px] text-ink-tertiary">
          IC-weighted composite · holdout 2023-2025
        </span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {TIER_DISPLAY.map(({ key, label, badge }) => {
          const rows = byTier[key] ?? []
          if (rows.length === 0) return null
          const isIndustry = badge.startsWith('★')
          return (
            <div key={key}>
              <div className="flex items-baseline gap-2 mb-2">
                <h3 className="font-sans text-xs font-semibold text-ink-primary">
                  {label}
                </h3>
                <span
                  className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
                    isIndustry
                      ? 'bg-teal/10 text-teal border-teal/30'
                      : 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30'
                  }`}
                >
                  {badge}
                </span>
              </div>
              <ul className="space-y-1">
                {rows.slice(0, 5).map((r) => {
                  const score = Math.round(Number(r.conviction_score) * 100)
                  const symbol = r.symbol ?? r.instrument_id.slice(0, 8)
                  return (
                    <li
                      key={r.instrument_id}
                      className="flex items-baseline justify-between text-xs py-1 border-b border-paper-rule/40"
                    >
                      <Link
                        href={`/stocks/${encodeURIComponent(symbol)}`}
                        className="font-mono text-xs font-semibold text-ink-primary hover:text-teal"
                      >
                        {symbol}
                      </Link>
                      <span className="font-sans text-[10px] text-ink-tertiary truncate flex-1 mx-2">
                        {r.sector ?? '—'}
                      </span>
                      <span
                        className="font-mono text-xs text-ink-primary tabular-nums"
                        data-validator-id={`stock.conviction_score:${r.instrument_id}`}
                        data-validator-raw={r.conviction_score != null ? String(r.conviction_score) : '—'}
                      >
                        {score}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
    </section>
  )
}
