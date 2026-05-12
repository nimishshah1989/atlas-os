// SP07 — Specialist agent chat UI.
// Free-form question → /api/agents/invoke → SEBI-safe narrative answer
// with optional tool-call audit trail. The orchestrator picks the right
// specialist (regime_watcher, sector_rotation, stock_screener,
// drift_detector) based on the question's keywords.
import { AgentChatClient } from '@/components/intelligence/AgentChatClient'

export const dynamic = 'force-dynamic'

const AGENT_DESCRIPTIONS: { name: string; tagline: string; example: string }[] = [
  {
    name: 'regime_watcher',
    tagline: 'Current market regime + deployment multiplier + breadth signals',
    example: 'What is the current market regime?',
  },
  {
    name: 'sector_rotation',
    tagline: 'Which sectors are leading / improving / weakening / lagging today',
    example: 'Which sectors are in the leading quadrant?',
  },
  {
    name: 'stock_screener',
    tagline:
      'Top stocks by conviction or RS — sector-filter or industry-grade-only',
    example: 'Top 5 highest-conviction stocks in industry-grade tiers',
  },
  {
    name: 'drift_detector',
    tagline: 'Data-quality findings from the validator agent (P0/P1/P2/P3)',
    example: 'Any P0 or P1 data anomalies in the last 7 days?',
  },
]

export default function AgentsChatPage() {
  return (
    <main className="max-w-3xl mx-auto px-6 sm:px-10 py-8 bg-white min-h-screen">
      <header className="mb-6">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Intelligence · Agents
        </div>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Ask Atlas</h1>
        <p className="font-sans text-sm text-ink-secondary mt-1 max-w-2xl">
          Type a question. The orchestrator routes it to one of four
          specialists; the answer is grounded in live data via read-only
          tool calls. No advice, no opinions — measurements and rankings.
        </p>
      </header>

      <section className="mb-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {AGENT_DESCRIPTIONS.map((a) => (
          <div
            key={a.name}
            className="border border-paper-rule rounded-sm p-3 bg-paper-rule/10"
          >
            <div className="font-mono text-[11px] text-teal font-semibold">
              {a.name}
            </div>
            <div className="font-sans text-xs text-ink-secondary mt-1 leading-snug">
              {a.tagline}
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary mt-1 italic">
              e.g. &ldquo;{a.example}&rdquo;
            </div>
          </div>
        ))}
      </section>

      <AgentChatClient />

      <footer className="mt-8 pt-4 border-t border-paper-rule font-sans text-[10px] text-ink-tertiary">
        Powered by Groq Llama 3.3 70B. SEBI-safe banned-word scan runs on
        every response — any forbidden word in the output aborts the
        invocation with a hard error.
      </footer>
    </main>
  )
}
