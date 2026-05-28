'use client'
// frontend/src/components/v6/sectors/SectorCardsGrid.tsx
// 3-col grid of 30 sector cards — Page 04 Sectors.
// Source: mv_sector_cards (latest snapshot, ~30 rows).

import Link from 'next/link'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  return {
    text: `${pct >= 0 ? '+' : ''}${pct.toFixed(decimals)}%`,
    cls: pct >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function fmtPp(v: number | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const pp = v * 100
  return {
    text: `${pp >= 0 ? '+' : ''}${pp.toFixed(1)}pp`,
    cls: pp >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

// ── Verdict chip ──────────────────────────────────────────────────────────────

function VerdictMini({ abbr }: { abbr: string | null }) {
  if (!abbr) return null
  const cls =
    abbr === 'OW' ? 'bg-signal-pos text-paper'
    : abbr === 'UW' ? 'bg-signal-neg text-paper'
    : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'
  return (
    <span
      className={`inline-flex items-center font-mono text-[9px] font-bold uppercase tracking-[0.12em] px-[5px] py-[2px] rounded-[2px] ${cls}`}
      aria-label={abbr === 'OW' ? 'Overweight' : abbr === 'UW' ? 'Underweight' : 'Neutral'}
    >
      {abbr}
    </span>
  )
}

// ── Individual sector card ────────────────────────────────────────────────────

function SectorCard({ card, rank }: { card: SectorCardRow; rank: number }) {
  const r1m = fmtPct(card.ret_1m)
  const r3m = fmtPct(card.ret_3m)
  const rs3m = fmtPp(card.rs_3m)
  const isOW = card.verdict_abbr === 'OW'
  const isUW = card.verdict_abbr === 'UW'

  return (
    <Link
      href={`/sectors/${encodeURIComponent(card.sector_name)}`}
      className={[
        'block bg-paper border border-paper-rule rounded-[2px] p-5 cursor-pointer',
        'transition-colors hover:bg-paper-soft hover:border-ink-rule',
        'text-inherit no-underline',
        isOW ? 'border-l-[3px] border-l-signal-pos' : '',
        isUW ? 'border-l-[3px] border-l-signal-neg' : '',
      ].join(' ')}
      aria-label={`${card.sector_name} sector card`}
      data-testid={`sector-card-${card.sector_name}`}
    >
      {/* Head */}
      <div className="flex items-baseline justify-between mb-2">
        <div className="font-serif text-[20px] text-ink-primary leading-[1.2]">
          {card.sector_name}
        </div>
        <div className="flex items-center gap-1.5">
          <VerdictMini abbr={card.verdict_abbr} />
          <span className="font-mono text-[11px] text-ink-tertiary">#{rank}</span>
        </div>
      </div>

      {/* Constituent count */}
      <div className="font-sans text-[11px] text-ink-tertiary mb-3">
        {card.constituent_count} stocks{card.buy_signal_count > 0 ? ` · ${card.buy_signal_count} BUY open` : ''}
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <div className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">1M return</div>
          <div className={`font-mono text-[18px] font-medium mt-0.5 ${r1m.cls}`}>
            {r1m.text}
          </div>
        </div>
        <div>
          <div className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">3M RS vs N500</div>
          <div className={`font-mono text-[18px] font-medium mt-0.5 ${rs3m.cls}`}>
            {rs3m.text}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-paper-rule pt-3 flex items-center justify-between">
        <div className="font-sans text-[11px] text-ink-tertiary">
          3M abs: <span className={`font-mono font-medium ${r3m.cls}`}>{r3m.text}</span>
        </div>
        <div className="font-sans text-[11px] text-ink-tertiary">
          {card.pct_above_ema20 != null
            ? `${Math.round(card.pct_above_ema20 * 100)}% >EMA20`
            : card.vol_60d_ann != null
            ? `vol ${Math.round((card.vol_60d_ann ?? 0) * 100)}%`
            : ''}
        </div>
      </div>
    </Link>
  )
}

// ── Main grid component ───────────────────────────────────────────────────────

export function SectorCardsGrid({ cards }: { cards: SectorCardRow[] }) {
  if (cards.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-32 bg-paper border border-paper-rule rounded-[2px] text-ink-tertiary text-sm"
        role="status"
      >
        No sector card data available.
      </div>
    )
  }

  // Sort: Overweight first, then Neutral, then Underweight, stable within each
  const sorted = [...cards].sort((a, b) => {
    const order = (v: string | null) =>
      v === 'OW' ? 0 : v === 'NW' ? 1 : v === 'UW' ? 2 : 3
    const diff = order(a.verdict_abbr) - order(b.verdict_abbr)
    if (diff !== 0) return diff
    return (b.rs_3m ?? -Infinity) - (a.rs_3m ?? -Infinity)
  })

  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
      aria-label="Sector cards grid"
      data-testid="sector-cards-grid"
    >
      {sorted.map((card, idx) => (
        <SectorCard key={card.sector_name} card={card} rank={idx + 1} />
      ))}
    </div>
  )
}
