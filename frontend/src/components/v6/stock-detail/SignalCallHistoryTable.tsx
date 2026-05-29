// Audit ledger of every atlas_signal_calls event for a stock.
// Pure server component. Renders as a compact table.

import Link from 'next/link'
import type { SignalCallEvent } from '@/lib/queries/v6/recent_signal_calls'

interface SignalCallHistoryTableProps {
  events: SignalCallEvent[]
}

const ACTION_COLOR: Record<string, string> = {
  POSITIVE: 'text-signal-pos',
  NEGATIVE: 'text-signal-neg',
  NEUTRAL:  'text-ink-3',
}

function fmtPct(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v)
  if (Number.isNaN(n)) return '—'
  return `${(n * 100).toFixed(1)}%`
}

export function SignalCallHistoryTable({ events }: SignalCallHistoryTableProps) {
  if (events.length === 0) {
    return (
      <p className="font-sans text-[12px] text-ink-3 italic">
        No signal_call events recorded for this stock yet.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px] font-mono">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="text-left  py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Cell</th>
            <th className="text-left  py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Tier · Tenure</th>
            <th className="text-left  py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Action</th>
            <th className="text-left  py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Entered</th>
            <th className="text-left  py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Exited</th>
            <th className="text-right py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Confidence</th>
            <th className="text-right py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Predicted Excess</th>
            <th className="text-left  py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          {events.map(ev => (
            <tr key={ev.signal_call_id} className="border-b border-paper-rule last:border-0 hover:bg-paper-deep/50">
              <td className="py-2 px-2">
                <Link href={`/cells/${ev.cell_id}`} className="text-accent hover:underline">{ev.cell_id.slice(0, 8)}…</Link>
              </td>
              <td className="py-2 px-2 text-ink">{ev.cap_tier} · {ev.tenure}</td>
              <td className={`py-2 px-2 ${ACTION_COLOR[ev.action] ?? 'text-ink-3'}`}>{ev.action}</td>
              <td className="py-2 px-2 text-ink-3">{ev.entry_date}</td>
              <td className="py-2 px-2 text-ink-3">{ev.exit_date ?? '—'}</td>
              <td className="py-2 px-2 text-right text-ink">{fmtPct(ev.confidence_unconditional)}</td>
              <td className="py-2 px-2 text-right text-ink">{fmtPct(ev.predicted_excess)}</td>
              <td className="py-2 px-2">
                {ev.is_active ? (
                  <span className="inline-block px-1.5 py-0.5 rounded-[2px] bg-signal-pos text-white font-mono text-[9px]">OPEN</span>
                ) : (
                  <span className="inline-block px-1.5 py-0.5 rounded-[2px] bg-paper-deep text-ink-3 font-mono text-[9px] border border-paper-rule">CLOSED</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
