// OwnSectorStrip — the stock's OWN sector index, inline on the v4 stock detail page
// (FM 2026-06-26). Reads the same fresh mv_sector_cards row the Sectors pages use, so the
// stock is always framed against where its sector sits. Pure server component, real data,
// v4 design tokens. (Distinct from the legacy SectorContextStrip on the flag-off path.)
import Link from 'next/link'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

// mv_sector_cards returns are FRACTIONS (e.g. 0.0329) — ×100 for display.
function pct(v: number | null, d = 1): string {
  return v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`
}
function tone(v: number | null): string {
  return v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'
}

function Metric({ label, v }: { label: string; v: number | null }) {
  return (
    <div className="text-right">
      <p className="font-num text-[9px] uppercase tracking-[0.12em] text-txt-3">{label}</p>
      <p className={`font-num text-[15px] font-medium tabular-nums ${tone(v)}`}>{pct(v)}</p>
    </div>
  )
}

const VERDICT_TONE: Record<string, string> = {
  Overweight: 'border-sig-pos/30 text-sig-pos',
  Underweight: 'border-sig-neg/30 text-sig-neg',
  Neutral: 'border-edge-rule text-txt-2',
}

export function OwnSectorStrip({ card, symbol }: { card: SectorCardRow | null; symbol: string }) {
  if (!card) return null
  const vtone = VERDICT_TONE[card.verdict] ?? 'border-edge-rule text-txt-2'
  const breadth = card.pct_above_ema21 != null ? `${Math.round(card.pct_above_ema21 * 100)}%` : '—'
  return (
    <section className="border-b border-edge-hair px-8 py-5">
      <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
        <div className="mr-auto">
          <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Own sector index</p>
          <Link
            href={`/sectors/${encodeURIComponent(card.sector_name)}`}
            className="font-display text-[19px] font-medium tracking-tight text-txt-1 hover:text-brand"
          >
            {card.sector_name} <span className="text-txt-3">↗</span>
          </Link>
        </div>
        <span className={`rounded-tile border px-2 py-0.5 font-num text-[11px] font-semibold uppercase tracking-wider ${vtone}`}>
          {card.verdict}
        </span>
        <Metric label="1M" v={card.ret_1m} />
        <Metric label="3M" v={card.ret_3m} />
        <Metric label="1Y" v={card.ret_12m} />
        <div className="text-right">
          <p className="font-num text-[9px] uppercase tracking-[0.12em] text-txt-3">Breadth &gt;EMA21</p>
          <p className="font-num text-[15px] font-medium tabular-nums text-txt-1">{breadth}</p>
        </div>
      </div>
      <p className="mt-2 font-sans text-[12px] leading-[1.5] text-txt-3">
        How {symbol}&rsquo;s own sector index is moving — context for reading the stock&rsquo;s six lenses.
      </p>
    </section>
  )
}
