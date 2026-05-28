// frontend/src/components/v6/stocks/HeroStories.tsx
// Page 05 · Hero stories — 4 narrative blocks:
//   1. Fresh BUYs today
//   2. Fresh AVOIDs today
//   3. Highest conviction BUYs
//   4. Exit candidates (degrading composites)
// Server component — no client state needed.

import type { HeroStories as HeroStoriesData, HeroStock } from '@/lib/queries/v6/stocks-landscape'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtComposite(v: string | null): string {
  if (v === null) return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  return n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1)
}

function fmtRs3m(v: string | null): string {
  if (v === null) return '—'
  const n = parseFloat(v) * 100
  if (isNaN(n)) return '—'
  return n >= 0 ? `+${n.toFixed(1)}pp` : `${n.toFixed(1)}pp`
}

function compositeColor(v: string | null, forAction?: string | null): string {
  if (forAction === 'AVOID') return 'text-signal-warn'
  const n = v ? parseFloat(v) : NaN
  if (isNaN(n)) return 'text-ink-tertiary'
  if (n >= 4) return 'text-signal-pos'
  if (n <= -4) return 'text-signal-neg'
  return 'text-signal-warn'
}

type DotColor = 'green' | 'red' | 'amber'

function dotStyle(color: DotColor): string {
  const map: Record<DotColor, string> = {
    green: 'bg-signal-pos',
    red: 'bg-signal-neg',
    amber: 'bg-signal-warn',
  }
  return map[color]
}

function pillStyle(color: 'green' | 'red' | 'amber' | 'info'): string {
  const map = {
    green: 'bg-signal-pos/10 text-signal-pos',
    red: 'bg-signal-neg/10 text-signal-neg',
    amber: 'bg-signal-warn/10 text-signal-warn',
    info: 'bg-signal-info/13 text-signal-info',
  }
  return map[color]
}

// ---------------------------------------------------------------------------
// StockRow — single stock line in a story block
// ---------------------------------------------------------------------------

function StockRow({
  stock,
  dotColor,
  valueText,
  valueClass,
  metaSuffix,
}: {
  stock: HeroStock
  dotColor: DotColor
  valueText: string
  valueClass: string
  metaSuffix?: string
}) {
  const tenureLabel =
    stock.matrix_tenure_dominant && stock.matrix_action_sign
      ? `${stock.cap_tier.charAt(0)} ${stock.matrix_tenure_dominant} ${stock.matrix_action_sign}`
      : null

  return (
    <div className="grid grid-cols-[8px_1fr_auto] gap-2 items-start py-[7px] border-b border-dashed border-paper-rule last:border-b-0">
      <span
        className={`inline-block w-[7px] h-[7px] rounded-full mt-1 shrink-0 ${dotStyle(dotColor)}`}
      />
      <div>
        <span className="font-mono font-semibold text-ink-primary text-[11.5px]">
          {stock.symbol}
        </span>
        <div className="font-sans text-[10.5px] text-ink-tertiary mt-0.5 leading-snug">
          {stock.sector ?? '—'} ·{' '}
          <span className="font-mono text-ink-secondary">{stock.cap_tier}</span>
          {tenureLabel && (
            <>
              {' '}· Cell <span className="font-mono text-ink-secondary">{tenureLabel}</span>
            </>
          )}
          {metaSuffix && <> · {metaSuffix}</>}
        </div>
      </div>
      <span className={`font-mono text-[11px] font-semibold ${valueClass}`}>{valueText}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// StoryBlock — one column
// ---------------------------------------------------------------------------

function StoryBlock({
  eyeLabel,
  pillText,
  pillColor,
  title,
  stocks,
  dotColor,
  tailText,
  renderValue,
  renderValueClass,
  metaSuffix,
}: {
  eyeLabel: string
  pillText: string
  pillColor: 'green' | 'red' | 'amber' | 'info'
  title: string
  stocks: HeroStock[]
  dotColor: DotColor
  tailText: string
  renderValue: (s: HeroStock) => string
  renderValueClass: (s: HeroStock) => string
  metaSuffix?: (s: HeroStock) => string | undefined
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="font-sans text-[10px] tracking-[0.18em] uppercase text-ink-tertiary font-semibold">
          {eyeLabel}
        </span>
        <span
          className={`font-mono text-[9px] px-[6px] py-[1px] rounded-[2px] font-semibold tracking-[0.04em] ${pillStyle(pillColor)}`}
        >
          {pillText}
        </span>
      </div>
      <div className="font-serif text-[15px] text-ink-primary mb-2 leading-snug">{title}</div>

      {stocks.length === 0 ? (
        <div className="font-sans text-[11px] text-ink-tertiary py-2">No data available</div>
      ) : (
        stocks.map(s => (
          <StockRow
            key={s.symbol}
            stock={s}
            dotColor={dotColor}
            valueText={renderValue(s)}
            valueClass={renderValueClass(s)}
            metaSuffix={metaSuffix?.(s)}
          />
        ))
      )}

      <div className="mt-[10px] pt-[10px] border-t border-paper-rule font-sans text-[11px] text-ink-tertiary leading-relaxed">
        {tailText}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// HeroStories — main export
// ---------------------------------------------------------------------------

export function HeroStories({ data }: { data: HeroStoriesData }) {
  const { freshBuys, freshAvoids, highConfBuys, exitCandidates } = data

  return (
    <section className="py-9 border-b border-paper-rule">
      <div className="max-w-[1400px] mx-auto px-8">
        <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
          <div>
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-none">
              Today&apos;s story
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1 max-w-[760px] leading-snug">
              Four narrative blocks built from per-instrument signal data. Numbers are deterministic — each line re-renders nightly. Use these to know{' '}
              <em>where to look first</em> before opening the full table.
            </p>
          </div>
        </div>

        <div
          className="bg-paper-soft border border-paper-rule rounded-sm mt-6 p-[22px] grid gap-6"
          style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}
        >
          {/* Block 1: Top BUYs by composite */}
          <StoryBlock
            eyeLabel="Top BUYs by composite"
            pillText={`${freshBuys.length} names`}
            pillColor="green"
            title="Highest composite score BUYs — strong positive methodology signal"
            stocks={freshBuys}
            dotColor="green"
            tailText="Top BUYs by composite score. Sorted by methodology conviction, not price momentum."
            renderValue={s => fmtComposite(s.composite_score)}
            renderValueClass={() => 'text-signal-pos'}
          />

          {/* Block 2: Worst AVOIDs by composite */}
          <StoryBlock
            eyeLabel="Worst AVOIDs by composite"
            pillText={`${freshAvoids.length} names`}
            pillColor="red"
            title="Lowest composite score AVOIDs — strongest deterioration signal"
            stocks={freshAvoids}
            dotColor="red"
            tailText="Stocks with the most negative composite scores. Avoid signals active."
            renderValue={s => fmtComposite(s.composite_score)}
            renderValueClass={() => 'text-signal-neg'}
          />

          {/* Block 3: High-conviction BUYs */}
          <StoryBlock
            eyeLabel="High-conviction BUYs"
            pillText={`stack of ${data.stats.highConfBuyCount} HIGH`}
            pillColor="info"
            title="Composite ≥ +4 + industry-grade confidence"
            stocks={highConfBuys}
            dotColor="green"
            tailText="Industry-grade confidence + strong composite. These are the highest-conviction long candidates in tonight's run."
            renderValue={s => fmtComposite(s.composite_score)}
            renderValueClass={() => 'text-signal-pos'}
          />

          {/* Block 4: Exit candidates */}
          <StoryBlock
            eyeLabel="Exit candidates"
            pillText={`${exitCandidates.length} degrading`}
            pillColor="amber"
            title="BUY/WATCH positions with composite below +2 — early warning"
            stocks={exitCandidates}
            dotColor="amber"
            tailText="Composite decay typically precedes a state transition by 5–10 sessions. Watch these for AVOID fires."
            renderValue={s => `${fmtRs3m(s.rs_3m_nifty500)}`}
            renderValueClass={() => 'text-signal-warn'}
            metaSuffix={s =>
              s.composite_score
                ? `Comp ${fmtComposite(s.composite_score)}`
                : undefined
            }
          />
        </div>
      </div>
    </section>
  )
}
