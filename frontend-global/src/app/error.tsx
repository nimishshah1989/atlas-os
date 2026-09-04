'use client'
// src/app/error.tsx — a render failure says what failed and what to do.
import { PageHeader } from '@/components/ui/PageHeader'

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="page">
      <PageHeader title="This page failed to render" />
      <p className="max-w-[64ch] text-body text-ink-2">
        {error.message || 'An unexpected error stopped the page.'} Try again; if it keeps failing, the health page
        shows whether the database and the last pipeline run are in order.
      </p>
      <button type="button" onClick={reset} className="btn mt-4">
        Try again
      </button>
    </div>
  )
}
