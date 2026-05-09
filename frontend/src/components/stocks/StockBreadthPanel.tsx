import type { StockRowWithSector } from '@/lib/queries/stocks'

function pctOwRs(arr: StockRowWithSector[]): number | null {
  if (arr.length === 0) return null
  return arr.filter(s => s.rs_state === 'Overweight_RS').length / arr.length
}

function pctImpr(arr: StockRowWithSector[]): number | null {
  if (arr.length === 0) return null
  return arr.filter(s => s.momentum_state === 'Improving').length / arr.length
}

function pctFmt(v: number | null): string {
  if (v == null) return '—'
  return `${Math.round(v * 100)}%`
}

function owRsColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  return v >= 0.6 ? 'text-signal-pos' : v >= 0.4 ? 'text-signal-warn' : 'text-signal-neg'
}

function imprColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  return v >= 0.5 ? 'text-signal-pos' : v >= 0.3 ? 'text-signal-warn' : 'text-signal-neg'
}

function Tile({ label, arr }: { label: string; arr: StockRowWithSector[] }) {
  const ow = pctOwRs(arr)
  const im = pctImpr(arr)
  return (
    <div className="flex flex-col gap-1 px-4 py-2.5 border border-paper-rule rounded-sm min-w-[110px]">
      <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary mb-0.5">
        {label}
        <span className="font-normal normal-case tracking-normal ml-1 text-ink-tertiary/60">({arr.length})</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="font-sans text-[10px] text-ink-tertiary">OW RS</span>
        <span className={`font-mono text-xs tabular-nums font-semibold ${owRsColor(ow)}`}>{pctFmt(ow)}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="font-sans text-[10px] text-ink-tertiary">Impr</span>
        <span className={`font-mono text-xs tabular-nums font-semibold ${imprColor(im)}`}>{pctFmt(im)}</span>
      </div>
    </div>
  )
}

export function StockBreadthPanel({
  stocks,
  above30wMaCount,
}: {
  stocks: StockRowWithSector[]
  above30wMaCount: number
}) {
  const total = stocks.length
  const maPct = total > 0 ? above30wMaCount / total : 0
  const maBarColor = maPct >= 0.6 ? '#2F6B43' : maPct >= 0.4 ? '#f59e0b' : '#ef4444'

  const n50 = stocks.filter(s => s.in_nifty_50)
  const n100 = stocks.filter(s => s.in_nifty_100)
  const n500 = stocks.filter(s => s.in_nifty_500)

  return (
    <div className="flex flex-wrap items-stretch gap-4 px-4 py-3 border border-paper-rule rounded-sm bg-paper">
      {/* Big number */}
      <div className="flex flex-col justify-center gap-1.5 min-w-[200px]">
        <div className="flex items-baseline gap-1.5">
          <span className="font-mono text-2xl font-semibold text-ink-primary tabular-nums">{above30wMaCount}</span>
          <span className="font-sans text-xs text-ink-tertiary">of {total} stocks</span>
        </div>
        <div className="font-sans text-[10px] text-ink-secondary">above 30-week MA</div>
        <div className="w-full h-1.5 bg-paper-rule rounded-full overflow-hidden mt-0.5">
          <div
            className="h-full rounded-full"
            style={{ width: `${Math.round(maPct * 100)}%`, background: maBarColor }}
          />
        </div>
        <div className="font-mono text-[10px] tabular-nums" style={{ color: maBarColor }}>
          {Math.round(maPct * 100)}% participation
        </div>
      </div>

      {/* Divider */}
      <div className="hidden sm:block w-px bg-paper-rule self-stretch" />

      {/* Mini tiles */}
      <div className="flex flex-wrap gap-2">
        <Tile label="Nifty 50" arr={n50} />
        <Tile label="Nifty 100" arr={n100} />
        <Tile label="Nifty 500" arr={n500} />
        <Tile label="All" arr={stocks} />
      </div>
    </div>
  )
}
