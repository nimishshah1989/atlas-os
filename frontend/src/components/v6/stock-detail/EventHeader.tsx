// frontend/src/components/v6/stock-detail/EventHeader.tsx
interface EventHeaderProps {
  symbol: string
  companyName: string
  sector: string | null
  indexBadges: string[]
  state: string | null
  dwellDays: number | null
  peerRank: number | null
  peerTotal: number
  convictionDirection: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | null
  convictionTenure: string | null
  convictionScore: number | null
  currentPrice: number | null
  ret3m: number | null
  rsVsNifty: number | null
}

const STAGE_META: Record<string, { label: string; color: string }> = {
  stage_1:      { label: 'STAGE 1 BASE',         color: 'text-ink-3' },
  stage_2a:     { label: 'STAGE 2A BREAKOUT',     color: 'text-signal-pos' },
  stage_2b:     { label: 'STAGE 2B CONFIRMED',    color: 'text-signal-pos' },
  stage_2c:     { label: 'STAGE 2C MATURE',       color: 'text-signal-warn' },
  stage_3:      { label: 'STAGE 3 TOP',           color: 'text-signal-warn' },
  stage_4:      { label: 'STAGE 4 DECLINE',       color: 'text-signal-neg' },
  uninvestable: { label: 'UNINVESTABLE',           color: 'text-signal-neg' },
}

const CONVICTION_META: Record<string, { label: string; cls: string }> = {
  POSITIVE: { label: 'BULLISH',  cls: 'bg-signal-pos text-white' },
  NEGATIVE: { label: 'BEARISH',  cls: 'bg-signal-neg text-white' },
  NEUTRAL:  { label: 'NEUTRAL',  cls: 'bg-paper-deep text-ink-3 border border-paper-rule' },
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  return `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

function fmtRsPctile(v: number | null): string {
  if (v == null) return '—'
  return `${Math.round(v * 100)}`
}

export function EventHeader({
  symbol, companyName, sector, indexBadges, state, dwellDays,
  peerRank, peerTotal, convictionDirection, convictionTenure, convictionScore,
  currentPrice, ret3m, rsVsNifty,
}: EventHeaderProps) {
  const stageMeta = state ? (STAGE_META[state] ?? { label: state.toUpperCase(), color: 'text-ink-3' }) : null
  const convMeta = convictionDirection ? CONVICTION_META[convictionDirection] : null

  return (
    <section className="px-6 py-5 border-b border-paper-rule bg-paper">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
        <span className="font-mono text-[28px] font-semibold text-ink leading-none">{symbol}</span>
        <span className="font-sans text-base text-ink-3 leading-none">{companyName}</span>
        {sector && (
          <span className="inline-block border border-paper-rule rounded-[2px] px-2 py-0.5 font-mono text-[10px] text-ink-4 tracking-wide">
            {sector}
          </span>
        )}
        {indexBadges.map(badge => (
          <span key={badge} className="inline-block border border-paper-rule rounded-[2px] px-2 py-0.5 font-mono text-[10px] text-ink-4 tracking-wide">
            {badge}
          </span>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-4">
        {stageMeta && (
          <span className={`font-mono text-[11px] font-semibold tracking-wider ${stageMeta.color}`}>
            {stageMeta.label}
          </span>
        )}
        {dwellDays !== null && (
          <span className="font-sans text-[12px] text-ink-3">· {dwellDays} day{dwellDays !== 1 ? 's' : ''}</span>
        )}
        {peerRank !== null && (
          <span className="font-sans text-[12px] text-ink-3">· Rank {peerRank} of {peerTotal}</span>
        )}
        {convMeta && (
          <span className={`inline-block px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold tracking-wider ${convMeta.cls}`}>
            {convMeta.label}{convictionTenure ? ` ${convictionTenure.toUpperCase()}` : ''}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCell label="Price" value={fmtPrice(currentPrice)} valueClass="text-ink" />
        <MetricCell label="3M Return" value={fmtPct(ret3m)} valueClass={ret3m == null ? 'text-ink-3' : ret3m >= 0 ? 'text-signal-pos' : 'text-signal-neg'} />
        <MetricCell label="RS Percentile" value={fmtRsPctile(rsVsNifty)} valueClass={rsVsNifty == null ? 'text-ink-3' : rsVsNifty >= 0.8 ? 'text-signal-pos' : rsVsNifty >= 0.5 ? 'text-ink' : 'text-signal-neg'} unit="/100" />
        <MetricCell label="Conviction" value={convictionScore != null ? convictionScore.toFixed(2) : '—'} valueClass={convictionScore == null ? 'text-ink-3' : convictionScore >= 0.6 ? 'text-signal-pos' : convictionScore <= 0.4 ? 'text-signal-neg' : 'text-ink'} />
      </div>
    </section>
  )
}

function MetricCell({ label, value, valueClass, unit }: { label: string; value: string; valueClass: string; unit?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">{label}</p>
      <p className={`font-mono text-[18px] font-semibold leading-none ${valueClass}`}>
        {value}{unit && <span className="font-sans text-[10px] text-ink-3 ml-0.5">{unit}</span>}
      </p>
    </div>
  )
}
