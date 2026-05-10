import Link from 'next/link'

export default function FundNotFound() {
  return (
    <div className="max-w-[1200px] mx-auto px-6 py-16 text-center">
      <p className="font-sans text-sm text-ink-secondary mb-4">Fund not found.</p>
      <Link href="/funds" className="font-sans text-xs text-teal hover:underline">
        ← Back to Funds
      </Link>
    </div>
  )
}
