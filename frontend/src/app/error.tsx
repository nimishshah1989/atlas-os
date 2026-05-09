// src/app/error.tsx
'use client'
import { useEffect } from 'react'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => { console.error(error) }, [error])

  return (
    <div className="p-8 max-w-md mx-auto mt-16">
      <p className="font-sans text-sm text-ink-secondary mb-4">
        Something went wrong loading this page.
      </p>
      <button
        onClick={reset}
        className="font-sans text-sm text-accent underline"
      >
        Try again
      </button>
    </div>
  )
}
