// allow-large: Atlas methodology — thin server wrapper; content lives in MethodologyTabs
export const dynamic = 'force-dynamic'

import { getActiveWeightSetsWithTrail } from '@/lib/queries/weight_performance'
import { MethodologyTabs } from '@/components/methodology/MethodologyTabs'

export default async function MethodologyPage() {
  const activeSets = await getActiveWeightSetsWithTrail()
  const sets = activeSets.map(s => ({ tier: s.tier, predicted_ic: s.predicted_ic ?? null }))

  return (
    <main className="max-w-3xl mx-auto px-6 sm:px-10 py-10 bg-white min-h-screen">
      <header className="mb-8">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Methodology
        </div>
        <h1 className="font-serif text-3xl text-ink-primary mt-1">
          How Atlas Thinks
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-xl">
          The v2 decision engine: layered targets, Policy rails, the 6-step flow, Weinstein stage classification, and the hybrid sector + fund classifiers — written for daily use.
        </p>
      </header>

      <MethodologyTabs activeSets={sets} />

      <footer className="mt-14 pt-6 border-t border-paper-rule font-sans text-[10px] text-ink-tertiary">
        Last methodology revision: 2026-05-20 · Atlas-OS v2 (Wave 4B) — v2 decision engine
      </footer>
    </main>
  )
}
