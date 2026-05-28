'use client'

// frontend/src/components/v6/etfs/HeroStories.tsx
//
// Four narrative blocks for Page 07 ETFs list:
//   1. Cleanest BUYs — action=BUY sorted by composite_score desc
//   2. Tightest tracking — sorted by te_60d asc (null last)
//   3. Liquidity warnings — adv_20d_inr < 30_000_000 (₹3 cr)
//   4. Premium-to-NAV outliers — |premium_bps| > 25
//
// All data derived from EtfListV6Row[] passed as prop (34 rows max — pure JS).
// Atlas Javeri visual language: paper/ink tokens, font-serif headings.

import type { EtfListV6Row } from '@/lib/queries/v6/etfs'

// ── Formatting helpers ────────────────────────────────────────────────────────

function fmtBps(v: number | null): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(0)} bps`
}

function fmtAdv(v: number | null): string {
  if (v == null) return '—'
  const cr = v / 1e7
  return `₹${cr.toFixed(1)} cr`
}

function fmtScore(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}`
}

function fmtTe(v: number | null): string {
  if (v == null) return '—'
  // te_60d from MV is already in bps (numeric 4dp)
  // If value < 1 treat as fractional, else already bps
  const bps = v < 1 ? v * 10000 : v
  return `${bps.toFixed(0)} bps`
}

// ── Story row component ───────────────────────────────────────────────────────

function StoryRow({
  ticker,
  subtitle,
  value,
  dotColor,
  valueColor,
}: {
  ticker: string
  subtitle: string
  value: string
  dotColor: 'green' | 'amber' | 'red'
  valueColor: 'pos' | 'neg' | 'warn'
}) {
  const dotClass =
    dotColor === 'green'
      ? 'bg-signal-pos'
      : dotColor === 'amber'
        ? 'bg-signal-warn'
        : 'bg-signal-neg'

  const valClass =
    valueColor === 'pos'
      ? 'text-signal-pos'
      : valueColor === 'neg'
        ? 'text-signal-neg'
        : 'text-signal-warn'

  return (
    <div className="grid grid-cols-[8px_1fr_auto] gap-2 items-start py-1.5 border-b border-dashed border-paper-rule last:border-b-0">
      <span
        className={`w-2 h-2 rounded-full mt-1 shrink-0 ${dotClass}`}
        aria-hidden="true"
      />
      <div>
        <div className="font-mono font-semibold text-ink-primary text-[11px] tracking-tight">
          {ticker}
        </div>
        <div className="font-sans text-[10.5px] text-ink-tertiary mt-0.5 leading-tight">
          {subtitle}
        </div>
      </div>
      <span className={`font-mono text-[11px] font-semibold tabular-nums ${valClass}`}>
        {value}
      </span>
    </div>
  )
}

// ── Story block ───────────────────────────────────────────────────────────────

function StoryBlock({
  eyeLabel,
  pillLabel,
  pillVariant,
  title,
  children,
  tail,
}: {
  eyeLabel: string
  pillLabel: string
  pillVariant: 'green' | 'red' | 'amber' | 'info'
  title: string
  children: React.ReactNode
  tail: string
}) {
  const pillClass: Record<string, string> = {
    green: 'bg-signal-pos/10 text-signal-pos',
    red: 'bg-signal-neg/10 text-signal-neg',
    amber: 'bg-signal-warn/10 text-signal-warn',
    info: 'bg-signal-info/10 text-signal-info',
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="font-sans text-[10px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold">
          {eyeLabel}
        </span>
        <span
          className={`font-mono text-[9px] px-1.5 py-0.5 rounded-sm font-semibold tracking-wide ${pillClass[pillVariant]}`}
        >
          {pillLabel}
        </span>
      </div>
      <div className="font-serif text-[15px] text-ink-primary mb-2 leading-snug">
        {title}
      </div>
      <div className="space-y-0">{children}</div>
      <div className="mt-2.5 pt-2.5 border-t border-paper-rule font-sans text-[11px] text-ink-tertiary leading-relaxed">
        {tail}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export interface HeroStoriesProps {
  etfs: EtfListV6Row[]
}

export function HeroStories({ etfs }: HeroStoriesProps) {
  // 1. Cleanest BUYs: action=BUY, sort by composite_score desc, top 5
  const cleanBuys = etfs
    .filter((e) => e.action === 'BUY')
    .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0))
    .slice(0, 5)

  // 2. Tightest TE: sort by te_60d asc, null last, top 5
  const tightestTe = [...etfs]
    .filter((e) => e.te_60d != null)
    .sort((a, b) => (a.te_60d ?? Infinity) - (b.te_60d ?? Infinity))
    .slice(0, 5)

  // 3. Liquidity warnings: adv_20d_inr < 3cr (3e7 INR)
  const liquidityWarnings = etfs
    .filter((e) => e.adv_20d_inr != null && e.adv_20d_inr < 3e7)
    .sort((a, b) => (a.adv_20d_inr ?? 0) - (b.adv_20d_inr ?? 0))
    .slice(0, 5)

  // 4. Premium outliers: |premium_bps| > 25
  const premiumOutliers = etfs
    .filter((e) => e.premium_bps != null && Math.abs(e.premium_bps) > 25)
    .sort((a, b) => Math.abs(b.premium_bps ?? 0) - Math.abs(a.premium_bps ?? 0))
    .slice(0, 5)

  const buyCount = cleanBuys.length
  const teCount = tightestTe.filter((e) => {
    const bps = (e.te_60d ?? 1) < 1 ? (e.te_60d ?? 1) * 10000 : e.te_60d ?? 1
    return bps < 10
  }).length
  const liqCount = liquidityWarnings.length
  const premCount = premiumOutliers.length

  return (
    <div
      className="bg-paper-soft border border-paper-rule rounded-sm p-5 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6"
      data-testid="hero-stories"
    >
      {/* Block 1: Cleanest BUYs */}
      <StoryBlock
        eyeLabel="Cleanest BUYs"
        pillLabel={`${buyCount} names`}
        pillVariant="green"
        title="Cell-confirmed + tight tracking + liquid"
        tail="ETFs scoring BUY on Atlas composite — highest conviction picks across all categories."
      >
        {cleanBuys.map((e) => (
          <StoryRow
            key={e.ticker}
            ticker={e.ticker}
            subtitle={[
              e.etf_category,
              e.fund_house,
              e.te_60d != null ? `TE ${fmtTe(e.te_60d)}` : null,
              e.adv_20d_inr != null ? `ADV ${fmtAdv(e.adv_20d_inr)}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
            value={fmtScore(e.composite_score)}
            dotColor="green"
            valueColor="pos"
          />
        ))}
      </StoryBlock>

      {/* Block 2: Tightest TE */}
      <StoryBlock
        eyeLabel="Tightest tracking"
        pillLabel="TE < 10 bps"
        pillVariant="info"
        title="Best-in-class index reps · passive-purist stack"
        tail="Single-digit TE only achievable on broad-cap Indian indices + Gold. Sector ETFs structurally carry more TE."
      >
        {tightestTe.map((e) => (
          <StoryRow
            key={e.ticker}
            ticker={e.ticker}
            subtitle={`vs ${e.etf_category ?? 'index'} · ${fmtTe(e.te_60d)} · 60d`}
            value={fmtTe(e.te_60d)}
            dotColor="green"
            valueColor="pos"
          />
        ))}
      </StoryBlock>

      {/* Block 3: Liquidity warnings */}
      <StoryBlock
        eyeLabel="Liquidity warnings"
        pillLabel={`${liqCount} ETFs`}
        pillVariant="amber"
        title={`ADV < ₹3 cr · execution drag risk`}
        tail="Multiple AMCs duplicate Nifty-tracking ETFs but ADV is winner-take-all. First-mover liquidity moats make alternatives structurally thin."
      >
        {liquidityWarnings.length === 0 ? (
          <div className="font-sans text-[11px] text-ink-tertiary py-2">
            All ETFs above ₹3 cr ADV threshold today.
          </div>
        ) : (
          liquidityWarnings.map((e) => (
            <StoryRow
              key={e.ticker}
              ticker={e.ticker}
              subtitle={`${e.etf_category ?? '—'} · ${e.fund_house ?? '—'} · ADV ${fmtAdv(e.adv_20d_inr)}`}
              value={fmtAdv(e.adv_20d_inr)}
              dotColor="amber"
              valueColor="warn"
            />
          ))
        )}
      </StoryBlock>

      {/* Block 4: Premium-to-NAV outliers */}
      <StoryBlock
        eyeLabel="Premium-to-NAV outliers"
        pillLabel={`${premCount} ETFs`}
        pillVariant="red"
        title="Market price diverging from NAV by > ±25 bps"
        tail="Premium > +25bps signals AP arbitrage friction. Wait for gap compression before entering at NAV-fair-value."
      >
        {premiumOutliers.length === 0 ? (
          <div className="font-sans text-[11px] text-ink-tertiary py-2">
            All ETFs within ±25 bps of NAV today.
          </div>
        ) : (
          premiumOutliers.map((e) => (
            <StoryRow
              key={e.ticker}
              ticker={e.ticker}
              subtitle={`${e.etf_category ?? '—'} · ${e.fund_house ?? '—'} · premium ${fmtBps(e.premium_bps)}`}
              value={fmtBps(e.premium_bps)}
              dotColor="red"
              valueColor="neg"
            />
          ))
        )}
      </StoryBlock>
    </div>
  )
}

export default HeroStories
