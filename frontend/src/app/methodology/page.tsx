// allow-large: thin server wrapper around MethodologyV61 client component
export const dynamic = 'force-dynamic'

import MethodologyV61 from '@/components/methodology/MethodologyV61'

export const metadata = {
  title: 'How Atlas thinks · Methodology',
  description: 'Atlas v6.1 methodology — interactive explainer of the engine, math, and limits.',
}

export default function MethodologyPage() {
  return (
    <main className="min-h-screen bg-paper">
      <MethodologyV61 />
    </main>
  )
}
