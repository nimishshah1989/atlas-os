export const revalidate = 300

import Link from 'next/link'
import { SignalQuality } from '@/components/methodology/SignalQuality'
import { getSignalQuality } from '@/lib/queries/signal_quality'

export const metadata = {
  title: 'Signal quality · Does the scoring actually work?',
  description:
    'The measured predictive power of every Atlas lens: rank-IC, hit rate and decile spread against realised forward returns, reported per era, per horizon and per cap band — including the lenses that show no evidence.',
}

export default async function SignalQualityPage() {
  const rows = await getSignalQuality()
  return (
    <main className="min-h-screen bg-surface-base">
      <div className="mx-auto flex max-w-[1100px] items-center justify-end px-6 pt-4">
        <Link href="/methodology"
          className="rounded-tile border border-edge-rule px-3 py-1.5 font-num text-[12px] text-txt-1 no-underline hover:bg-surface-raised">
          ← How every score is built
        </Link>
      </div>
      <SignalQuality rows={rows} />
    </main>
  )
}
