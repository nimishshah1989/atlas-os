// src/app/not-found.tsx — an address with nothing behind it yet.
import Link from 'next/link'
import { PageHeader } from '@/components/ui/PageHeader'

export default function NotFound() {
  return (
    <div className="page">
      <PageHeader title="Nothing here yet" />
      <p className="max-w-[64ch] text-body text-ink-2">
        This address has no page behind it. Sections arrive as the pipeline fills them; today the{' '}
        <Link href="/" className="text-accent">
          Today
        </Link>{' '}
        page and{' '}
        <Link href="/health" className="text-accent">
          Health
        </Link>{' '}
        are live.
      </p>
    </div>
  )
}
