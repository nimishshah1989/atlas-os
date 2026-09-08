// src/components/health/ProviderCallsTable.tsx — what the run date spent of each provider's budget:
// calls per (provider, endpoint) as every script recorded them, plain numbers, nothing derived.
import { formatNum, formatShortDateTime } from '@/lib/format'
import type { ProviderCallsSnapshot } from '@/lib/queries/health'

export function ProviderCallsTable({ snapshot }: { snapshot: ProviderCallsSnapshot }) {
  const { rows } = snapshot
  return (
    <div className="panel overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Endpoint</th>
            <th className="r">Calls</th>
            <th>Updated (ET)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.provider}:${r.endpoint}`} data-provider-call={`${r.provider}:${r.endpoint}`}>
              <td className="text-ink">{r.provider}</td>
              <td className="max-w-[48ch] truncate text-ink-2" title={r.endpoint}>
                {r.endpoint}
              </td>
              <td className="num r">{formatNum(r.calls)}</td>
              <td className="num whitespace-nowrap">{formatShortDateTime(r.updated_at)}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="text-ink-3">
                No provider calls recorded yet. Every ingest script adds its request counts when it commits.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
