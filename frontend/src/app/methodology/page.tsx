// allow-large: thin server wrapper around MethodologyV62 client component
export const dynamic = 'force-dynamic'

import MethodologyV62 from '@/components/methodology/MethodologyV62'

export const metadata = {
  title: 'How Atlas thinks · Methodology',
  description: 'Atlas v6.2 methodology — deep interactive explainer: engine, cells, conviction math, flywheel, auto-optimization loop.',
}

export default function MethodologyPage() {
  return (
    <main className="min-h-screen bg-paper">
      <MethodologyV62 />
    </main>
  )
}
