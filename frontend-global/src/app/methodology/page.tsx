// src/app/methodology/page.tsx — the glass box: what a score means and what it is made of.
//
// The lens list and the threshold values are READ, never restated here. A page that hardcoded
// "technical 0.35" would be a second source of truth and would be wrong the first time the FM
// re-tunes a weight from the thresholds table — and being wrong on the page that explains the
// numbers is worse than having no page.
import { MethodologyBody } from '@/components/methodology/MethodologyBody'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { getLensWeights, getTierRules, type LensWeight } from '@/lib/queries/methodology'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Methodology' }

const STATE: Record<LensWeight['state'], { word: string; tone: string }> = {
  computed: { word: 'computed · blended', tone: 'text-pos' },
  partial: { word: 'partly computed · blended', tone: 'text-pos' },
  overlay: { word: 'computed · overlay, weight 0', tone: 'text-warn' },
  absent: { word: 'no producer yet — absent, not zero', tone: 'text-ink-3' },
}

export default async function MethodologyPage() {
  await requireUser()
  const [weights, tiers] = await Promise.all([attempt(getLensWeights()), attempt(getTierRules())])
  return (
    <div className="page">
      <PageHeader
        title="Methodology"
        lead="How a score on this board is built, what it is made of, and what it does not yet know. Open any section."
      />

      {weights.ok ? (
        <div className="panel mt-4 overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-meta text-ink-3">
                <th className="px-3 py-2 text-left font-medium">Lens</th>
                <th className="px-3 py-2 text-right font-medium">Weight</th>
                <th className="px-3 py-2 text-left font-medium">Reads</th>
                <th className="px-3 py-2 text-left font-medium">State today</th>
              </tr>
            </thead>
            <tbody>
              {weights.value.map((w) => (
                <tr key={w.lens} className="border-t border-hair">
                  <td className="px-3 py-2 text-table text-ink">{w.label}</td>
                  <td className="px-3 py-2 text-right text-table num text-ink-2">
                    {(Number(w.weight) * 100).toFixed(0)}%
                  </td>
                  <td className="px-3 py-2 text-table text-ink-2">{w.reads}</td>
                  <td className="px-3 py-2 text-table">
                    <span className={STATE[w.state].tone} title={w.note}>{STATE[w.state].word}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <QueryFailed error={weights.error} />
      )}

      {weights.ok && <MethodologyBody lenses={weights.value} tiers={tiers.ok ? tiers.value : []} />}

      <p className="mt-8 max-w-[70ch] text-meta text-ink-3">
        Every weight and cut point above is a row in the thresholds table, read on each run. This
        page describes the rules; the table holds the values; the nightly applies them. There is no
        third place where a number could hide.
      </p>
    </div>
  )
}
