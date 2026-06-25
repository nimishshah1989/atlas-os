// src/app/admin/thresholds/page.tsx
// v4 read-only Thresholds view — the methodology constants that drive the engine,
// grouped by category from atlas.atlas_thresholds. (Replaces the old redirect to
// /admin/policies, which no longer exists.) Edits go through the policy flow with
// an audit trail; this surface is read-only.
import { getAllThresholds, type ThresholdRow } from '@/lib/queries/thresholds'
import { Panel } from '@/components/v4/ui/Panel'
import { formatThreshold } from '@/lib/format-number'

export const dynamic = 'force-dynamic'

const Head = ({ children, right }: { children: React.ReactNode; right?: boolean }) => (
  <th className={`px-2 py-2 font-num text-[9px] uppercase tracking-[0.12em] text-txt-3 ${right ? 'text-right' : 'text-left'}`}>{children}</th>
)

export default async function ThresholdsPage() {
  const rows = await getAllThresholds().catch(() => [] as ThresholdRow[])
  const byCat = new Map<string, ThresholdRow[]>()
  for (const r of rows) {
    const arr = byCat.get(r.category) ?? []
    arr.push(r)
    byCat.set(r.category, arr)
  }

  return (
    <div className="mx-auto max-w-[1280px] px-6 py-7 space-y-6">
      <div>
        <p className="font-num text-[10px] uppercase tracking-[0.18em] text-txt-3">Admin · Methodology</p>
        <h1 className="mt-1 font-display text-[30px] font-bold tracking-tight text-txt-1">Thresholds</h1>
        <p className="mt-1.5 max-w-[760px] font-sans text-[13px] text-txt-2">
          The methodology constants that drive the engine — loaded from <span className="font-num text-txt-1">atlas.atlas_thresholds</span>.
          Read-only here; changes are made through the policy flow with a full audit trail.
        </p>
      </div>

      {rows.length === 0 ? (
        <Panel title="No thresholds"><p className="font-sans text-[13px] text-txt-2">Could not load thresholds.</p></Panel>
      ) : (
        [...byCat.entries()].map(([cat, list]) => (
          <Panel key={cat} eyebrow="Category" title={cat} bodyClassName="px-2 pb-3 pt-1">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-edge-rule">
                  <Head>Key</Head><Head right>Value</Head><Head right>Default</Head><Head right>Range</Head><Head>Description</Head>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.threshold_key} className="border-b border-edge-hair align-top last:border-0">
                    <td className="px-2 py-2 font-num text-[12px] text-txt-1">
                      {r.threshold_key}{r.units ? <span className="text-txt-3"> ({r.units})</span> : null}
                    </td>
                    <td className="px-2 py-2 text-right font-num text-[12px] tabular-nums text-txt-1">{formatThreshold(r.threshold_value)}</td>
                    <td className="px-2 py-2 text-right font-num text-[11px] tabular-nums text-txt-3">{formatThreshold(r.default_value)}</td>
                    <td className="px-2 py-2 text-right font-num text-[11px] tabular-nums text-txt-3">{formatThreshold(r.min_allowed)}–{formatThreshold(r.max_allowed)}</td>
                    <td className="max-w-[420px] px-2 py-2 font-sans text-[12px] text-txt-2">
                      {r.description}{r.methodology_section ? <span className="text-txt-3"> · §{r.methodology_section}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        ))
      )}
    </div>
  )
}
