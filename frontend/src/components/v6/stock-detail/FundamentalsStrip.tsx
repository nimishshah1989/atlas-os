// frontend/src/components/v6/stock-detail/FundamentalsStrip.tsx
//
// The /v1/tv/metrics endpoint serializes Decimal columns as JSON strings
// ("22.1341"), so these fields arrive as string at runtime even though the
// API type declares number. Accept both and coerce before formatting —
// calling .toFixed() on the raw string throws and crashes the page render.
type Num = number | string | null

interface FundamentalsStripProps {
  pe: Num
  ps: Num
  pb: Num
  debtToEquity: Num
  roe: Num
}

function toNum(v: Num): number | null {
  if (v == null) return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

function fmt(v: Num, decimals = 1): string {
  const n = toNum(v)
  return n == null ? '—' : n.toFixed(decimals)
}

function fmtRoe(v: Num): string {
  const n = toNum(v)
  return n == null ? '—' : `${n.toFixed(1)}%`
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
