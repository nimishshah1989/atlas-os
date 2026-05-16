'use client'

type Props = {
  ticker: string
  grossPnl: number
  holdingDays: number
  stcgRate: number
  ltcgRate: number
  signalStrength: number
}

export function TaxHarvestingAlert({ ticker, grossPnl, holdingDays, stcgRate, ltcgRate, signalStrength }: Props) {
  const daysToLtcg = 365 - holdingDays
  const stcgTax = grossPnl * stcgRate
  const ltcgTax = grossPnl * ltcgRate
  const saving = stcgTax - ltcgTax
  const isWeak = signalStrength < 0.6

  if (daysToLtcg > 60 || saving < 5000 || grossPnl <= 0) return null

  return (
    <div className="border border-amber-300 bg-amber-50 rounded-[2px] p-4 mt-3">
      <p className="font-sans text-xs font-semibold text-amber-800 uppercase tracking-wide mb-2">Tax Opportunity</p>
      <p className="font-sans text-sm text-amber-900">
        Holding <strong>{ticker}</strong> for {daysToLtcg} more days converts this gain to LTCG.
        Potential saving: <strong>₹{Math.round(saving).toLocaleString('en-IN')}</strong>
      </p>
      <p className="font-sans text-xs text-amber-700 mt-2">
        Signal: <strong>{isWeak ? 'WEAK' : 'STRONG'}</strong> ({signalStrength.toFixed(2)}/1.0)
        {isWeak ? ' — consider holding' : ' — follow discipline'}
      </p>
      <div className="flex gap-3 mt-3">
        <button className="font-sans text-xs border border-amber-600 text-amber-700 px-3 py-1.5 rounded-[2px] hover:bg-amber-100">Hold — Save Tax</button>
        <button className="font-sans text-xs border border-ink-tertiary text-ink-secondary px-3 py-1.5 rounded-[2px] hover:bg-paper-rule">Exit Now — Follow Signal</button>
      </div>
    </div>
  )
}
