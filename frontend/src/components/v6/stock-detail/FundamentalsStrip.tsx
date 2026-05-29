// frontend/src/components/v6/stock-detail/FundamentalsStrip.tsx
interface FundamentalsStripProps {
  pe: number | null
  ps: number | null
  pb: number | null
  debtToEquity: number | null
  roe: number | null
}

function fmt(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function fmtRoe(v: number | null): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

function Pill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-start gap-0.5 px-3 py-2 border border-paper-rule rounded bg-paper-deep">
      <span className="font-mono text-[9px] uppercase tracking-wider text-ink-3">{label}</span>
      <span className="font-mono text-[15px] text-ink leading-none">{value}</span>
    </div>
  )
}

export function FundamentalsStrip({ pe, ps, pb, debtToEquity, roe }: FundamentalsStripProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <Pill label="P/E" value={fmt(pe)} />
      <Pill label="P/S" value={fmt(ps)} />
      <Pill label="P/B" value={fmt(pb)} />
      <Pill label="Debt/Eq" value={fmt(debtToEquity)} />
      <Pill label="ROE" value={fmtRoe(roe)} />
    </div>
  )
}
