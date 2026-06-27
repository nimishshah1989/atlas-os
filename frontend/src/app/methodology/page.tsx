// allow-large: thin server wrapper around MethodologyV62 client component
export const revalidate = 300

import MethodologyV62 from '@/components/methodology/MethodologyV62'

export const metadata = {
  title: 'How Atlas thinks · Methodology',
  description: 'Atlas v6.2 methodology — deep interactive explainer: engine, cells, conviction math, flywheel, auto-optimization loop.',
}

export default function MethodologyPage() {
  return (
    <main className="min-h-screen bg-surface-base">
      <div className="mx-auto flex max-w-[1100px] items-center justify-end px-6 pt-4">
        <a href="/thresholds"
          className="rounded-tile border border-edge-rule px-3 py-1.5 font-num text-[12px] text-txt-1 no-underline hover:bg-surface-raised">
          Control panel — edit thresholds &amp; weights →
        </a>
      </div>
      <MethodologyV62 />
    </main>
  )
}
