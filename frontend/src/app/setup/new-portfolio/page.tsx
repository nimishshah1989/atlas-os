// src/app/setup/new-portfolio/page.tsx
// Portfolio creation page — RSC shell ≤250 LOC.
// Delegates form logic to NewPortfolioForm (client island).
import Link from 'next/link'
import { NewPortfolioForm } from '@/components/setup/NewPortfolioForm'

export default function SetupNewPortfolioPage() {
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-3xl mx-auto">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs font-sans text-ink-tertiary mb-3">
          <Link href="/setup" className="hover:text-ink-primary transition-colors">
            Setup
          </Link>
          <span>/</span>
          <span>New Portfolio</span>
        </div>
        <h1 className="font-serif text-2xl text-ink-primary">New Portfolio</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Create a named portfolio. Add holdings from the portfolio detail page after creation.
        </p>
      </header>

      <NewPortfolioForm />
    </main>
  )
}
