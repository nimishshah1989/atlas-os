// frontend/src/components/DataSourceBanner.tsx
//
// Thin strip surfacing the data source + the snapshot/data-as-of date.
// Sits below the page title row. Never larger than 28px tall.
//
// All v6 pages now render directly from Supabase Postgres (no API fallback),
// so the default label is "Live Supabase". `source` is still accepted for
// the matrix page which retains the api/v1 demo-fallback path for cell
// definitions.

import { formatIST } from '@/lib/format-date'

type Props = {
  /** "live" → Live Supabase; "demo" → Demo fixture (matrix page only). */
  source?: 'live' | 'demo'
  /** ISO snapshot/data-as-of date (e.g. "2026-05-22") or full timestamp. */
  asOf: string
  hint?: string
}

function isDateOnly(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s)
}

export function DataSourceBanner({ source = 'live', asOf, hint }: Props) {
  const isLive = source === 'live'
  const label = isLive ? 'Live Supabase' : 'Demo data'
  const dot = isLive ? 'bg-signal-pos' : 'bg-signal-warn'
  // For pure ISO dates (snapshot_date columns) render as "snapshot YYYY-MM-DD";
  // for full timestamps (e.g. api/v1 envelope.data_as_of) keep the IST format.
  const asOfText = isDateOnly(asOf) ? `snapshot ${asOf}` : `Data as of ${formatIST(asOf)}`
  return (
    <div className="px-6 py-1.5 border-b border-paper-rule/60 flex items-center gap-3 bg-paper">
      <span className="inline-flex items-center gap-1.5 font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className="text-ink-secondary">{label}</span>
      </span>
      <span className="font-sans text-[10px] text-ink-tertiary">
        {asOfText}
      </span>
      {hint && (
        <span className="font-sans text-[10px] text-ink-tertiary ml-auto">
          {hint}
        </span>
      )}
    </div>
  )
}
