'use client'
// frontend/src/components/v6/sectors/SectorHeroReadout.tsx
// Page 04 hero readout — 3-col layout: Leading / Lagging / Rotation pattern.
// Derived from mv_sector_cards rows (sorted by rs_3m).

import type { SectorCardRow, SectorRRGRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(decimals)}%`
}

function fmtPp(v: number | null): string {
  if (v == null) return '—'
  const pp = v * 100
  return `${pp >= 0 ? '+' : ''}${pp.toFixed(1)}pp`
}

// ── Sub-components ────────────────────────────────────────────────────────────

type DotColor = 'green' | 'red' | 'amber'

const DOT_COLORS: Record<DotColor, string> = {
  green: 'bg-signal-pos',
  red:   'bg-signal-neg',
  amber: 'bg-signal-warn',
}

function SectorRow({
  sector, color, subtitle, rsLabel,
}: {
  sector: SectorCardRow
  color: DotColor
  subtitle: string
  rsLabel: string
}) {
  const rsPositive = rsLabel.startsWith('+')
  return (
    <div className="grid grid-cols-[auto_1fr_auto] gap-2 items-start py-[7px] border-b border-dashed border-paper-rule last:border-b-0">
      <span
        className={`w-[7px] h-[7px] rounded-full mt-1 shrink-0 ${DOT_COLORS[color]}`}
        aria-hidden="true"
      />
      <div>
        <span className="font-semibold text-ink-primary text-[12px]">{sector.sector_name}</span>
        <div className="text-[11px] text-ink-tertiary leading-[1.4]">{subtitle}</div>
      </div>
      <span
        className={`font-mono text-[11px] font-semibold ${rsPositive ? 'text-signal-pos' : 'text-signal-neg'}`}
        aria-label={`RS vs Nifty 500: ${rsLabel}`}
      >
        {rsLabel}
      </span>
    </div>
  )
}

function BlockEye({
  label, count, color,
}: {
  label: string
  count: number
  color: DotColor
}) {
  const PILL_COLORS: Record<DotColor, string> = {
    green: 'bg-signal-pos/10 text-signal-pos',
    red:   'bg-signal-neg/10 text-signal-neg',
    amber: 'bg-signal-warn/10 text-signal-warn',
  }
  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-2">
      <span>{label}</span>
      <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded-[2px] font-semibold ${PILL_COLORS[color]}`}>
        {count} sector{count !== 1 ? 's' : ''}
      </span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function SectorHeroReadout({
  cards,
  rrg,
}: {
  cards: SectorCardRow[]
  rrg?: SectorRRGRow[]
}) {
  if (cards.length === 0) return null

  // Build quadrant lookup from mv_sector_rrg when available (M14 fix).
  // Falls back to rs_3m-based heuristic when RRG data is absent.
  const quadrantMap = new Map<string, string | null>()
  if (rrg) {
    for (const row of rrg) {
      quadrantMap.set(row.sector_name, row.quadrant_current)
    }
  }

  function getQuadrant(card: SectorCardRow): string {
    const fromRrg = quadrantMap.get(card.sector_name)
    if (fromRrg) return fromRrg
    // Fallback heuristic
    if ((card.rs_3m ?? 0) > 0) return 'Leading'
    return 'Lagging'
  }

  // Split by quadrant using mv_sector_rrg.quadrant_current (M14)
  // True per-quadrant counts drive the badges; the slices below are only the
  // rows we render. (H4: badge previously read the 4-row slice, contradicting the
  // RRG legend which counts the full quadrant.)
  const leadingAll   = cards.filter((c) => getQuadrant(c) === 'Leading').sort((a, b) => (b.rs_3m ?? 0) - (a.rs_3m ?? 0))
  const laggingAll   = cards.filter((c) => getQuadrant(c) === 'Lagging').sort((a, b) => (a.rs_3m ?? 0) - (b.rs_3m ?? 0))
  const improvingAll = cards.filter((c) => getQuadrant(c) === 'Improving')
  const weakeningAll = cards.filter((c) => getQuadrant(c) === 'Weakening')

  const leading   = leadingAll.slice(0, 4)
  const lagging   = laggingAll.slice(0, 5)
  const improving = improvingAll.slice(0, 4)
  const weakening = weakeningAll.slice(0, 3)

  const totalLeading = leadingAll.length
  const totalLagging = laggingAll.length

  return (
    <div
      className="bg-paper-soft border border-paper-rule rounded-[2px] p-6 mt-6"
      aria-label="Sector summary stories"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Column 1 — Leading */}
        <div>
          <BlockEye label="Leading sectors" count={totalLeading} color="green" />
          <div
            className="font-serif text-[16px] text-ink-primary mb-2"
            data-testid="leading-title"
          >
            {totalLeading > 0
              ? `${leading[0].sector_name}${totalLeading > 1 ? ` + ${totalLeading - 1} others` : ''} carrying the tape`
              : 'No leading sectors'}
          </div>

          {leading.map((s) => (
            <SectorRow
              key={s.sector_name}
              sector={s}
              color="green"
              subtitle={`1M ${fmtPct(s.ret_1m)} · 3M ${fmtPct(s.ret_3m)} · ${s.buy_signal_count} BUY firing · ${s.pct_above_ema20 != null ? `${Math.round(s.pct_above_ema20 * 100)}% >EMA20` : ''}`}
              rsLabel={fmtPp(s.rs_3m)}
            />
          ))}

          <div className="mt-[10px] pt-[10px] border-t border-paper-rule text-[11px] text-ink-tertiary leading-[1.5]">
            <strong className="text-ink-secondary font-medium">Leading:</strong>{' '}
            high RS-ratio + rising RS-momentum. These sectors show broadening participation
            and positive absolute returns. Overweight candidates.
          </div>
        </div>

        {/* Column 2 — Lagging */}
        <div>
          <BlockEye label="Lagging sectors" count={totalLagging} color="red" />
          <div className="font-serif text-[16px] text-ink-primary mb-2">
            {lagging.length > 0
              ? `Rate-sensitives & global-cyclicals under pressure`
              : 'No lagging sectors'}
          </div>

          {lagging.map((s) => (
            <SectorRow
              key={s.sector_name}
              sector={s}
              color="red"
              subtitle={`1M ${fmtPct(s.ret_1m)} · 3M ${fmtPct(s.ret_3m)} · ${s.buy_signal_count} BUY firing`}
              rsLabel={fmtPp(s.rs_3m)}
            />
          ))}

          <div className="mt-[10px] pt-[10px] border-t border-paper-rule text-[11px] text-ink-tertiary leading-[1.5]">
            <strong className="text-ink-secondary font-medium">Lagging:</strong>{' '}
            weak RS-ratio + falling RS-momentum. Underweight candidates in the current regime.
            Monitor for reversal signals before adding.
          </div>
        </div>

        {/* Column 3 — Rotation pattern */}
        <div>
          <BlockEye label="Rotation pattern" count={improvingAll.length + weakeningAll.length} color="amber" />
          <div className="font-serif text-[16px] text-ink-primary mb-2">
            Capital rotating between quadrants — watch the trail
          </div>

          {improving.slice(0, 3).map((s) => (
            <SectorRow
              key={s.sector_name}
              sector={s}
              color="amber"
              subtitle={`Improving — RS momentum turning up · ${fmtPct(s.ret_3m)} 3M`}
              rsLabel={fmtPp(s.rs_3m)}
            />
          ))}

          {weakening.slice(0, 2).map((s) => (
            <SectorRow
              key={s.sector_name}
              sector={s}
              color="red"
              subtitle={`Weakening — RS momentum fading · ${fmtPct(s.ret_3m)} 3M`}
              rsLabel={fmtPp(s.rs_3m)}
            />
          ))}

          <div className="mt-[10px] pt-[10px] border-t border-paper-rule text-[11px] text-ink-tertiary leading-[1.5]">
            <strong className="text-ink-secondary font-medium">Read:</strong>{' '}
            sectors rotate counter-clockwise on the RRG: Leading → Weakening → Lagging → Improving.
            The trail below shows where each sector has been.
          </div>
        </div>

      </div>
    </div>
  )
}
