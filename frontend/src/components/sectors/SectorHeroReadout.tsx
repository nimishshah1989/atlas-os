'use client'
// frontend/src/components/sectors/SectorHeroReadout.tsx
// Page 04 hero readout — 3-col layout: Leading / Lagging / Rotation pattern.
//
// Derived from the CORRECTED sector-index returns (atlas_index_metrics_daily via
// getSectorIndexRs), NOT mv_sector_cards/mv_sector_rrg — those mirrors carried the
// row-offset-inflated returns and stale quadrants that put every sector in "Leading"
// (0 lagging) and showed Media at +51.8%. Leading/lagging is the sign of RS vs Nifty
// 500 over 3m; rotation is whether 1m RS is accelerating (improving) or fading
// (weakening) relative to 3m RS. Breadth/signal fields still come from the cards row.

import Link from 'next/link'

// One row of corrected sector data the readout renders.
export type SectorHeroRow = {
  sector_name: string
  ret_1m: number | null
  ret_3m: number | null
  rs_1m: number | null
  rs_3m: number | null
  pct_above_ema21: number | null
  buy_signal_count: number
}

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
  green: 'bg-sig-pos',
  red:   'bg-sig-neg',
  amber: 'bg-sig-warn',
}

function SectorRow({
  sector, color, subtitle, rsLabel,
}: {
  sector: SectorHeroRow
  color: DotColor
  subtitle: string
  rsLabel: string
}) {
  const rsPositive = rsLabel.startsWith('+')
  return (
    <Link
      href={`/sectors/${encodeURIComponent(sector.sector_name)}`}
      className="grid grid-cols-[auto_1fr_auto] gap-2 items-start py-[7px] border-b border-dashed border-edge-hair last:border-b-0 hover:bg-surface-raised rounded-tile transition-colors no-underline text-inherit -mx-2 px-2"
    >
      <span
        className={`w-[7px] h-[7px] rounded-full mt-1 shrink-0 ${DOT_COLORS[color]}`}
        aria-hidden="true"
      />
      <div>
        <span className="font-semibold text-txt-1 text-[12px] hover:text-brand transition-colors">{sector.sector_name}</span>
        <div className="text-[11px] text-txt-3 leading-[1.4]">{subtitle}</div>
      </div>
      <span
        className={`font-num text-[11px] font-semibold tabular-nums ${rsPositive ? 'text-sig-pos' : 'text-sig-neg'}`}
        aria-label={`RS vs Nifty 500: ${rsLabel}`}
      >
        {rsLabel}
      </span>
    </Link>
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
    green: 'bg-sig-pos/10 text-sig-pos',
    red:   'bg-sig-neg/10 text-sig-neg',
    amber: 'bg-sig-warn/10 text-sig-warn',
  }
  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-txt-3 font-semibold mb-2">
      <span>{label}</span>
      <span className={`font-num text-[9px] px-1.5 py-0.5 rounded-tile font-semibold tabular-nums ${PILL_COLORS[color]}`}>
        {count} sector{count !== 1 ? 's' : ''}
      </span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function SectorHeroReadout({
  rows,
}: {
  rows: SectorHeroRow[]
}) {
  if (rows.length === 0) return null

  // Leading vs lagging = sign of 3m RS vs Nifty 500 (did the sector beat the broad
  // market). Rotation = momentum: 1m RS accelerating above 3m RS (improving) or fading
  // below it (weakening). All from corrected returns — no stale-quadrant dependency.
  const rs3 = (c: SectorHeroRow) => c.rs_3m ?? 0
  const momentum = (c: SectorHeroRow) => (c.rs_1m ?? 0) - (c.rs_3m ?? 0)

  const leadingAll = rows.filter((c) => rs3(c) > 0).sort((a, b) => rs3(b) - rs3(a))
  const laggingAll = rows.filter((c) => rs3(c) <= 0).sort((a, b) => rs3(a) - rs3(b))
  // Improving: lagging on RS but momentum turning up. Weakening: leading but fading.
  const improvingAll = laggingAll.filter((c) => momentum(c) > 0).sort((a, b) => momentum(b) - momentum(a))
  const weakeningAll = leadingAll.filter((c) => momentum(c) < 0).sort((a, b) => momentum(a) - momentum(b))

  const leading   = leadingAll.slice(0, 4)
  const lagging   = laggingAll.slice(0, 5)
  const improving = improvingAll.slice(0, 4)
  const weakening = weakeningAll.slice(0, 3)

  const totalLeading = leadingAll.length
  const totalLagging = laggingAll.length

  return (
    <div
      className="rounded-tile border border-edge-hair bg-surface-inset/40 p-5"
      aria-label="Sector summary stories"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Column 1 — Leading */}
        <div>
          <BlockEye label="Leading sectors" count={totalLeading} color="green" />
          <div
            className="font-display text-[16px] text-txt-1 mb-2"
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
              subtitle={`1M ${fmtPct(s.ret_1m)} · 3M ${fmtPct(s.ret_3m)} · ${s.buy_signal_count} BUY firing · ${s.pct_above_ema21 != null ? `${Math.round(s.pct_above_ema21 * 100)}% >EMA21` : ''}`}
              rsLabel={fmtPp(s.rs_3m)}
            />
          ))}

          <div className="mt-[10px] pt-[10px] border-t border-edge-hair text-[11px] text-txt-3 leading-[1.5]">
            <strong className="text-txt-2 font-medium">Leading:</strong>{' '}
            high RS-ratio + rising RS-momentum. These sectors show broadening participation
            and positive absolute returns. Overweight candidates.
          </div>
        </div>

        {/* Column 2 — Lagging */}
        <div>
          <BlockEye label="Lagging sectors" count={totalLagging} color="red" />
          <div className="font-display text-[16px] text-txt-1 mb-2">
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

          <div className="mt-[10px] pt-[10px] border-t border-edge-hair text-[11px] text-txt-3 leading-[1.5]">
            <strong className="text-txt-2 font-medium">Lagging:</strong>{' '}
            weak RS-ratio + falling RS-momentum. Underweight candidates in the current regime.
            Monitor for reversal signals before adding.
          </div>
        </div>

        {/* Column 3 — Rotation pattern */}
        <div>
          <BlockEye label="Rotation pattern" count={improvingAll.length + weakeningAll.length} color="amber" />
          <div className="font-display text-[16px] text-txt-1 mb-2">
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

          <div className="mt-[10px] pt-[10px] border-t border-edge-hair text-[11px] text-txt-3 leading-[1.5]">
            <strong className="text-txt-2 font-medium">Read:</strong>{' '}
            sectors rotate counter-clockwise on the RRG: Leading → Weakening → Lagging → Improving.
            The trail below shows where each sector has been.
          </div>
        </div>

      </div>
    </div>
  )
}
