import type { USETFRow } from '@/lib/queries/us-etfs'

const RS_BG: Record<string, string> = {
  Leader:        'bg-signal-pos/20 border-signal-pos/30 text-signal-pos',
  Strong:        'bg-teal/15 border-teal/30 text-teal',
  Consolidating: 'bg-sky-100 border-sky-200 text-sky-700',
  Emerging:      'bg-amber-50 border-amber-200 text-amber-700',
  Average:       'bg-paper border-paper-rule text-ink-secondary',
  Weak:          'bg-orange-50 border-orange-200 text-orange-700',
  Laggard:       'bg-signal-neg/10 border-signal-neg/20 text-signal-neg',
}

const SECTOR_LABEL: Record<string, string> = {
  XLK:  'Technology',
  XLV:  'Health Care',
  XLF:  'Financials',
  XLY:  'Cons. Disc.',
  XLP:  'Cons. Stpl.',
  XLE:  'Energy',
  XLI:  'Industrials',
  XLB:  'Materials',
  XLRE: 'Real Estate',
  XLU:  'Utilities',
  XLC:  'Comm. Svcs.',
}

function fmtRet(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return (n >= 0 ? '+' : '') + n.toFixed(1) + '%'
}

function retColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

type Props = { etfs: USETFRow[] }

export function USSectorHeatmap({ etfs }: Props) {
  const sectorETFs = etfs.filter(e => {
    const cat = e.etf_category?.toLowerCase() ?? ''
    return cat.includes('sector')
  })

  if (sectorETFs.length === 0) {
    return (
      <div className="border border-paper-rule rounded-sm p-4">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
          Sector Rotation — US
        </div>
        <p className="font-sans text-xs text-ink-tertiary">No sector ETF data yet.</p>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-sm p-4">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
        Sector Rotation — US (Sector ETFs)
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
        {sectorETFs.map(etf => {
          const rsStyle = RS_BG[etf.rs_state ?? ''] ?? RS_BG['Average']
          return (
            <div
              key={etf.ticker}
              className={`rounded border p-2.5 ${rsStyle}`}
            >
              <div className="font-mono text-[11px] font-semibold">{etf.ticker}</div>
              <div className="font-sans text-[9px] opacity-70 mt-0.5 truncate">
                {SECTOR_LABEL[etf.ticker] ?? etf.linked_sector ?? etf.etf_category ?? ''}
              </div>
              <div className="mt-2 space-y-0.5">
                <div className="flex justify-between">
                  <span className="font-sans text-[9px] opacity-60">1M</span>
                  <span className={`font-mono text-[10px] ${retColor(etf.ret_1m)}`}>
                    {fmtRet(etf.ret_1m)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="font-sans text-[9px] opacity-60">3M</span>
                  <span className={`font-mono text-[10px] ${retColor(etf.ret_3m)}`}>
                    {fmtRet(etf.ret_3m)}
                  </span>
                </div>
              </div>
              <div className="mt-1.5 font-sans text-[9px] font-semibold opacity-80">
                {etf.rs_state ?? '—'}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
