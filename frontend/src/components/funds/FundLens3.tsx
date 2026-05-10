import { LensBar } from '@/components/ui/LensBar'
import type { FundLensRow } from '@/lib/queries/funds'

function Gate({ label, pass }: { label: string; pass: boolean | null }) {
  const icon = pass === true ? '✓' : pass === false ? '✗' : '?'
  const color =
    pass === true ? 'text-signal-pos' : pass === false ? 'text-signal-neg' : 'text-ink-tertiary'
  return (
    <div className="flex items-center gap-1">
      <span className={`font-mono text-xs font-semibold ${color}`}>{icon}</span>
      <span className="font-sans text-[10px] text-ink-tertiary">{label}</span>
    </div>
  )
}

export function FundLens3({
  lens,
  stocksGate,
  marketGate,
}: {
  lens: FundLensRow | null
  stocksGate: boolean | null
  marketGate: boolean | null
}) {
  const hasDisclosure = lens?.strong_aum_pct != null

  const segments = hasDisclosure
    ? [
        { pct: parseFloat(lens!.strong_aum_pct!), color: 'green' as const },
        { pct: parseFloat(lens!.unknown_aum_pct ?? '0'), color: 'neutral' as const },
        { pct: parseFloat(lens!.weak_aum_pct ?? '0'), color: 'red' as const },
      ]
    : []

  const asOfDate = lens?.as_of_date
    ? new Date(lens.as_of_date)
        .toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
        .replace(',', '')
    : undefined

  return (
    <div className="space-y-3">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        Holdings Lens
      </div>
      <LensBar
        segments={segments}
        label="Holdings"
        asOfDate={asOfDate}
        nullish={!hasDisclosure}
      />
      {!hasDisclosure && (
        <p className="font-sans text-[10px] text-ink-tertiary">
          No holdings disclosure available
        </p>
      )}
      <div className="space-y-1 pt-1 border-t border-paper-rule/40">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
          Gates
        </div>
        <Gate label="Stocks" pass={stocksGate} />
        <Gate label="Market" pass={marketGate} />
      </div>
      {lens?.holdings_concentration != null && (
        <div className="pt-1 border-t border-paper-rule/40">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
            Holdings Concentration
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-teal"
                style={{ width: `${Math.min(100, parseFloat(lens.holdings_concentration) * 100).toFixed(0)}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-ink-secondary tabular-nums">
              {(parseFloat(lens.holdings_concentration) * 100).toFixed(0)}%
            </span>
          </div>
          <p className="font-sans text-[9px] text-ink-tertiary mt-0.5">Top holding % of portfolio</p>
        </div>
      )}
    </div>
  )
}
