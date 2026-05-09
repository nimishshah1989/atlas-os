import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="max-w-[800px] mx-auto p-12 text-center">
      <h1 className="font-serif text-2xl font-semibold text-ink-primary mb-2">
        Stock not found
      </h1>
      <p className="font-sans text-sm text-ink-secondary mb-6">
        That symbol isn&apos;t in the current universe. It may be delisted,
        misspelled, or not yet classified in Atlas.
      </p>
      <Link
        href="/stocks"
        className="inline-block px-4 py-2 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary hover:bg-paper-rule/20"
      >
        ← Back to all stocks
      </Link>
    </div>
  )
}
