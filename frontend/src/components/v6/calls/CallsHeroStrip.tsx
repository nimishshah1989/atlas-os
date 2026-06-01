'use client'

// frontend/src/components/v6/calls/CallsHeroStrip.tsx
//
// Six-tile hero stats strip for /calls (Page 08 — Calls Performance).
// Displays: total fired, open, closed, BUY count, AVOID count, overall win rate,
// avg realized excess.
//
// Uses fmtSignedPct from calls.ts for sign-aware formatting (C2).
// "All positions active" text is conditional on closed count (M2).

import type { CallsHero } from '@/lib/queries/v6/calls'
import { fmtSignedPct } from '@/lib/format-number'
import { formatIST } from '@/lib/format-date'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'

interface CallsHeroStripProps {
  hero: CallsHero
}

interface Tile {
  label: string
  value: string
  valueClass?: string
  foot: string
  eli5Term?: string
}

export function CallsHeroStrip({ hero }: CallsHeroStripProps) {
  // C2: sign-aware formatter — negative values get '-', positive get '+'
  const realizedStr = fmtSignedPct(hero.avg_realized_excess)
  const realizedClass =
    hero.avg_realized_excess == null
      ? 'text-ink-primary'
      : hero.avg_realized_excess >= 0
        ? 'text-signal-pos'
        : 'text-signal-neg'

  const winRateStr =
    hero.overall_hit_rate != null
      ? `${(hero.overall_hit_rate * 100).toFixed(1)}%`
      : '—'

  // M2: conditional open/closed foot text
  const openFoot =
    hero.closed_calls === 0
      ? 'All positions currently active'
      : `${hero.open_calls} of ${hero.total_calls} still in flight`

  const closedPct =
    hero.total_calls > 0
      ? `${Math.round((hero.closed_calls / hero.total_calls) * 100)}%`
      : '0%'

  const tiles: Tile[] = [
    {
      label: 'Total fired',
      value: hero.total_calls.toLocaleString('en-IN'),
      foot: `${hero.buy_calls.toLocaleString('en-IN')} BUY · ${hero.avoid_calls.toLocaleString('en-IN')} AVOID`,
    },
    {
      label: 'Open',
      value: hero.open_calls.toLocaleString('en-IN'),
      valueClass: 'text-signal-warn',
      foot: openFoot,
    },
    {
      label: 'Closed',
      value: hero.closed_calls.toLocaleString('en-IN'),
      foot: `${closedPct} of fired calls closed`,
    },
    {
      label: 'Win rate',
      value: winRateStr,
      valueClass:
        hero.overall_hit_rate == null
          ? 'text-ink-primary'
          : hero.overall_hit_rate >= 0.5
            ? 'text-signal-pos'
            : 'text-signal-neg',
      foot: 'Calls that beat benchmark',
      eli5Term: 'ic_mean',
    },
    {
      label: 'BUY calls',
      value: hero.buy_calls.toLocaleString('en-IN'),
      valueClass: 'text-signal-pos',
      foot: 'POSITIVE direction signals',
    },
    {
      label: 'Avg realized ex.',
      value: realizedStr,
      valueClass: realizedClass,
      foot: 'Mean realized excess · all cells',
      eli5Term: 'ic_mean',
    },
  ]

  const dataAsOf = hero.data_as_of ? formatIST(hero.data_as_of) : '—'

  return (
    <div>
      <div
        className="grid grid-cols-6 bg-paper-soft border border-ink-rule rounded-[2px] overflow-hidden mt-6"
        aria-label="calls performance summary stats"
      >
        {tiles.map((tile, i) => (
          <div
            key={tile.label}
            className={`px-[18px] py-[14px] ${i < tiles.length - 1 ? 'border-r border-ink-rule' : ''}`}
          >
            <p className="text-[9px] font-semibold uppercase tracking-[0.18em] text-ink-4 mb-1">
              {tile.label}
            </p>
            <p
              className={`font-mono text-[22px] font-medium leading-none ${tile.valueClass ?? 'text-ink-primary'}`}
            >
              {tile.value}
            </p>
            <p className="text-[11px] text-ink-4 mt-1 leading-snug">
              {tile.eli5Term ? (
                <ELI5Tooltip term={tile.eli5Term}>{tile.foot}</ELI5Tooltip>
              ) : (
                tile.foot
              )}
            </p>
          </div>
        ))}
      </div>

      <p className="mt-2 text-[10px] font-mono text-ink-4">
        Data as of {dataAsOf} · mv_calls_performance ({hero.total_calls} calls · {hero.realized_count} with realized data)
      </p>
    </div>
  )
}
