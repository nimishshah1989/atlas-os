// DataStatusPanel — the Admin "Data status" tab. A simple RAG read of the data behind the live
// product: an overall health light, the atlas_foundation product tables (last update + lag +
// what each powers), the JIP inbound sources, and the recent pipeline runs. Server component —
// all data is fetched in the page and passed in. RULE #0: every date is a real MAX() from the table.
import type { FoundationFreshness, Rag, TableFreshness, PipelineRun } from '@/lib/queries/health'
import { jipLagThresholdDays } from '@/lib/queries/health'
import { JipSyncPanel } from '@/components/health/JipSyncPanel'
import { PipelineRunsTable } from '@/components/health/PipelineRunsTable'

const RAG_HEX: Record<Rag, string> = {
  green: 'var(--color-sig-pos)',
  amber: 'var(--color-sig-warn)',
  red: 'var(--color-sig-neg)',
}
const RAG_WORD: Record<Rag, string> = { green: 'All fresh', amber: 'Some lagging', red: 'Stale data' }

function Dot({ rag, size = 8 }: { rag: Rag; size?: number }) {
  return <span className="inline-block shrink-0 rounded-full" style={{ width: size, height: size, background: RAG_HEX[rag] }} />
}

const fmtDate = (d: Date | null) => (d == null ? '—' : new Date(d).toISOString().slice(0, 10))
const fmtLag = (n: number | null) => (n == null ? '—' : `${n}d`)
const fmtRows = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(0)}k` : String(n))

export function DataStatusPanel({
  foundation,
  jip,
  runs,
  overall,
  asOf,
}: {
  foundation: FoundationFreshness[]
  jip: TableFreshness[]
  runs: PipelineRun[]
  overall: Rag
  asOf: string | null
}) {
  const reds = foundation.filter((f) => f.rag === 'red').length
  const ambers = foundation.filter((f) => f.rag === 'amber').length
  return (
    <div className="space-y-6">
      {/* overall health banner */}
      <div
        className="flex items-center gap-3 rounded-tile border px-4 py-3"
        style={{ borderColor: `color-mix(in srgb, ${RAG_HEX[overall]} 40%, transparent)`, background: `color-mix(in srgb, ${RAG_HEX[overall]} 8%, transparent)` }}
      >
        <Dot rag={overall} size={12} />
        <div>
          <div className="font-display text-[16px] font-semibold" style={{ color: RAG_HEX[overall] }}>{RAG_WORD[overall]}</div>
          <div className="font-num text-[11px] text-txt-3">
            {foundation.length} product tables · {reds} stale · {ambers} lagging{asOf ? ` · checked ${asOf}` : ''}
          </div>
        </div>
      </div>

      {/* atlas_foundation product tables */}
      <section className="rounded-panel border border-edge-hair bg-surface-panel">
        <div className="border-b border-edge-hair px-4 py-2.5">
          <h2 className="font-display text-[15px] font-medium text-txt-1">Product data · atlas_foundation</h2>
          <p className="mt-0.5 font-sans text-[11px] text-txt-3">The tables the live site reads. Green = fresh for its cadence, amber = lagging, red = stale.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="tbl-centered w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-edge-rule font-num text-[10px] uppercase tracking-wider text-txt-3">
                <th className="px-4 py-1.5 text-left font-semibold">Table</th>
                <th className="px-2 py-1.5 text-left font-semibold">Powers</th>
                <th className="px-2 py-1.5 text-left font-semibold">Cadence</th>
                <th className="px-2 py-1.5 text-right font-semibold">Last update</th>
                <th className="px-2 py-1.5 text-right font-semibold">Lag</th>
                <th className="px-4 py-1.5 text-right font-semibold">Rows</th>
              </tr>
            </thead>
            <tbody>
              {foundation.map((f) => (
                <tr key={f.table} className="border-b border-edge-hair/60">
                  <td className="px-4 py-1.5">
                    <span className="flex items-center gap-2">
                      <Dot rag={f.rag} />
                      <span className="font-sans text-[12.5px] text-txt-1">{f.label}</span>
                    </span>
                    <span className="ml-4 font-num text-[10px] text-txt-3">{f.table}</span>
                  </td>
                  <td className="px-2 py-1.5 font-sans text-[11px] text-txt-2">{f.feeds}</td>
                  <td className="px-2 py-1.5 font-num text-[11px] text-txt-3">{f.cadence}</td>
                  <td className="px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-1">{fmtDate(f.latest_date)}</td>
                  <td className="px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums" style={{ color: RAG_HEX[f.rag] }}>{fmtLag(f.lag_days)}</td>
                  <td className="px-4 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-3">{fmtRows(f.row_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* JIP inbound sources (public.de_*) — reuse the existing panel (binary green/red by its own threshold) */}
      <JipSyncPanel rows={jip} />

      {/* recent pipeline runs */}
      <section className="rounded-panel border border-edge-hair bg-surface-panel p-4">
        <h2 className="mb-3 font-display text-[15px] font-medium text-txt-1">Recent pipeline runs</h2>
        <PipelineRunsTable runs={runs} />
      </section>

      <p className="font-sans text-[11px] leading-[1.6] text-txt-3">
        JIP threshold = {jipLagThresholdDays('')}d. Holdings tables refresh monthly, so a higher lag is normal there.
        Native from <strong className="text-txt-2">atlas_foundation</strong> + the JIP source sync.
      </p>
    </div>
  )
}
