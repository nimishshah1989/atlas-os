// src/app/setup/page.tsx
// Onboarding landing for the SETUP section.
// Thin shell ≤250 LOC — orientation text + two navigation cards.
import Link from 'next/link'

export default function SetupPage() {
  return (
    <main className="min-h-screen bg-surface-base px-8 py-6 max-w-4xl mx-auto">
      <header className="mb-8">
        <h1 className="font-display text-2xl text-txt-1">Setup</h1>
        <p className="font-sans text-sm text-txt-2 mt-2 max-w-xl">
          Configure Atlas to your desk — set your trade Policy and create portfolios.
          Every new portfolio inherits the house-default policy; override individual
          fields per-portfolio in Policy.
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Policy card */}
        <Link
          href="/setup/policy"
          className="group block p-5 border border-edge-hair rounded-tile bg-surface-panel shadow-tile hover:border-brand/40 transition-colors"
          aria-label="Policy — edit house-default and per-portfolio trade rules"
        >
          <h2 className="font-sans text-base font-semibold text-txt-1 group-hover:text-brand transition-colors">
            Policy
          </h2>
          <p className="font-sans text-xs text-txt-2 mt-1">
            Edit the house-default trade rules and override individual fields
            per portfolio: cash floor, position caps, entry / exit states, stops.
          </p>
          <span className="mt-3 inline-block font-sans text-xs text-brand">
            Go to Policy →
          </span>
        </Link>

        {/* New portfolio card */}
        <Link
          href="/setup/new-portfolio"
          className="group block p-5 border border-edge-hair rounded-tile bg-surface-panel shadow-tile hover:border-brand/40 transition-colors"
          aria-label="New Portfolio — create a new FM portfolio"
        >
          <h2 className="font-sans text-base font-semibold text-txt-1 group-hover:text-brand transition-colors">
            New Portfolio
          </h2>
          <p className="font-sans text-xs text-txt-2 mt-1">
            Create a new FM custom portfolio. Choose a name and instrument
            universe — the book inherits the house-default policy and you
            add holdings from the portfolio detail page.
          </p>
          <span className="mt-3 inline-block font-sans text-xs text-brand">
            Create Portfolio →
          </span>
        </Link>
      </div>
    </main>
  )
}
