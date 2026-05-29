// frontend/src/components/regime/TodayWorklist.tsx
// 3-count worklist: sectors entered favour / fresh breakouts / deteriorating holdings.
//
// 2026-05-29 (Batch 2): removed standalone "Fresh Breakouts" + "Review/Trim"
//   detail panels — they duplicated rows in the Top Conviction table below.
// 2026-05-29 (Batch 3): re-surfaced top-3 symbols PER CARD with "(dN)" day
//   counters so a fund-manager can see "JPPOWER (d3)" without scrolling.
//   Compact pill list inside the card itself; no separate section.
import Link from 'next/link'

export type SymbolWithDays = {
  symbol: string
  days: number | null
}

export type WorklistData = {
  sectorsEnteredFavour: number
  freshBreakouts: number
  breakoutSymbols: string[]
  /** Top breakout candidates with days-since-state-entry; subset of breakoutSymbols (same order). */
  breakoutDays: SymbolWithDays[]
  deterioratingCount: number
  deterioratingSymbols: string[]
  /** Top deterioration symbols with days-since-state-entry. */
  deterioratingDays: SymbolWithDays[]
}

type CountCardProps = {
  count: number
  label: string
  linkHref: string
  linkTestId: string
  sublabel?: string
  /** Top 3 symbols with day counters to surface inline. */
  symbols?: SymbolWithDays[]
  /** Colour accent for the symbol pills (pos = green, neg = red, neutral = ink). */
  tone?: 'pos' | 'neg' | 'neutral'
}

function toneClass(tone: 'pos' | 'neg' | 'neutral'): string {
  if (tone === 'pos') return 'text-signal-pos'
  if (tone === 'neg') return 'text-signal-neg'
  return 'text-ink-secondary'
}

// Compact pill: TICKER + "d3" suffix. Each ticker is a Link to its deep-dive
// page so the worklist remains the click-into-detail surface. Per the
// [[everything-clickable]] memory.
function SymbolPill({ s, tone }: { s: SymbolWithDays; tone: 'pos' | 'neg' | 'neutral' }) {
  return (
    <Link
      href={`/stocks/${encodeURIComponent(s.symbol)}`}
      className="font-mono text-[11px] leading-none whitespace-nowrap hover:underline"
    >
      <span className={`font-semibold ${toneClass(tone)}`}>{s.symbol}</span>
      {s.days != null && (
        <span className="text-ink-tertiary"> d{s.days}</span>
      )}
    </Link>
  )
}

// Card wrapper = div (not Link) so symbol pills can be their own anchors
// without nested-anchor invalid markup. The count/label region is a single
// Link to linkHref (the "view all" affordance); each symbol pill links
// directly to its stock detail page.
function CountCard({ count, label, linkHref, linkTestId, sublabel, symbols, tone = 'neutral' }: CountCardProps) {
  const top = symbols?.slice(0, 3) ?? []
  return (
    <div className="flex flex-col gap-1 border border-paper-rule rounded-sm px-4 py-3 hover:border-teal/40 hover:bg-teal/5 transition-colors group">
      <Link
        href={linkHref}
        data-testid={linkTestId}
        className="flex flex-col gap-1 -mx-1 px-1"
      >
        <span className="font-mono text-3xl font-semibold text-ink-primary group-hover:text-teal tabular-nums leading-none">
          {count}
        </span>
        <span className="font-sans text-xs text-ink-secondary leading-snug">{label}</span>
        {sublabel && (
          <span className="font-sans text-[10px] text-ink-tertiary">{sublabel}</span>
        )}
      </Link>
      {top.length > 0 && (
        <div className="flex flex-wrap gap-x-2 gap-y-1 mt-1.5 pt-1.5 border-t border-paper-rule/60">
          {top.map((s) => (
            <SymbolPill key={s.symbol} s={s} tone={tone} />
          ))}
        </div>
      )}
    </div>
  )
}

type Props = {
  data: WorklistData
}

export function TodayWorklist({ data }: Props) {
  const breakoutHref =
    data.breakoutSymbols.length > 0
      ? `/stocks/${encodeURIComponent(data.breakoutSymbols[0])}`
      : '/stocks'

  return (
    <div className="px-6 py-4 border-b border-paper-rule">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3">
        Today&apos;s Worklist
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <CountCard
          count={data.sectorsEnteredFavour}
          label="sectors entered favour"
          linkHref="/sectors"
          linkTestId="worklist-sectors-link"
          sublabel="new Overweight signals"
          tone="pos"
        />
        <CountCard
          count={data.freshBreakouts}
          label="fresh breakouts"
          linkHref={breakoutHref}
          linkTestId="worklist-breakout-link"
          sublabel="stage 2 entries"
          symbols={data.breakoutDays}
          tone="pos"
        />
        <CountCard
          count={data.deterioratingCount}
          label="holdings deteriorating"
          linkHref="/stocks?filter=deteriorating"
          linkTestId="worklist-deterioration-link"
          sublabel="stage 3/4 transitions"
          symbols={data.deterioratingDays}
          tone="neg"
        />
      </div>

    </div>
  )
}
