// allow-large: thin server wrapper around MethodologyV62 client component
export const revalidate = 300

import MethodologyV62 from '@/components/methodology/MethodologyV62'

export const metadata = {
  title: 'Methodology · How every score is built',
  description: 'How Atlas scores every stock across six lenses, blends four into a 0–100 conviction score, and rolls it up to sectors, funds and ETFs — with the real sub-components of each lens.',
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
