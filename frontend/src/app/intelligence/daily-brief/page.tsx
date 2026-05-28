// frontend/src/app/intelligence/daily-brief/page.tsx
// SP05 — server component that renders the latest Claude-authored brief.
// Atlas brand tokens (paper / ink / signal / teal), Tailwind classes only.

import { getLatestBrief } from '@/lib/queries/briefs'

export const dynamic = 'force-dynamic'
export const revalidate = 0

// DD-MMM-YYYY per project frontend convention (e.g. 12-May-2026)
function fmtDDMMMYYYY(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  const day = String(date.getUTCDate()).padStart(2, '0')
  const month = date.toLocaleString('en-IN', { month: 'short', timeZone: 'UTC' })
  const year = date.getUTCFullYear()
  return `${day}-${month}-${year}`
}

function fmtTimestampIST(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

// Regime → brand-token pill classes. Constructive is not in the global REGIME
// list (only Risk-On / Cautious / Risk-Off live in MarketRegimeBanner) but the
// brief table accepts it as a value, so map it to a neutral ink-tertiary tone.
const REGIME_PILL: Record<string, string> = {
  'Risk-On':       'bg-teal/10 text-teal border-teal/30',
  'Constructive':  'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30',
  'Cautious':      'bg-signal-warn/10 text-signal-warn border-signal-warn/30',
  'Risk-Off':      'bg-signal-neg/10 text-signal-neg border-signal-neg/30',
}

const SUMMARY_PILL: Record<string, string> = {
  bullish:   'bg-signal-pos/10 text-signal-pos border-signal-pos/30',
  neutral:   'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30',
  cautious:  'bg-signal-warn/10 text-signal-warn border-signal-warn/30',
  defensive: 'bg-signal-neg/10 text-signal-neg border-signal-neg/30',
}

function regimeDeltaIndicator(delta: string): { label: string; cls: string } | null {
  if (delta === 'upgraded') {
    return { label: '↑ Upgraded today', cls: 'text-signal-pos' }
  }
  if (delta === 'downgraded') {
    return { label: '↓ Downgraded today', cls: 'text-signal-neg' }
  }
  return null
}

export default async function DailyBriefPage() {
  const brief = await getLatestBrief()

  if (!brief) {
    return (
      <main className="max-w-[760px] mx-auto px-6 py-12">
        <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Daily Brief
        </div>
        <h1 className="font-serif text-3xl text-ink-primary mt-2 mb-4">
          No brief generated yet
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed">
          Run the brief generator to create one for the latest as-of date:
        </p>
        <pre className="mt-3 px-3 py-2 bg-paper-rule/40 font-mono text-xs text-ink-primary rounded-sm overflow-x-auto">
          <code>python scripts/generate_daily_brief.py --persist</code>
        </pre>
      </main>
    )
  }

  const regimePill = REGIME_PILL[brief.regime_state] ?? REGIME_PILL['Cautious']
  const summaryPill = SUMMARY_PILL[brief.regime_summary] ?? SUMMARY_PILL['neutral']
  const delta = regimeDeltaIndicator(brief.regime_delta)

  return (
    <main className="max-w-[760px] mx-auto px-6 py-12">
      <header className="border-b border-paper-rule pb-6 mb-8">
        <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Daily Brief
        </div>
        <h1 className="font-serif text-[36px] leading-[1.2] text-ink-primary mt-2 mb-3">
          {fmtDDMMMYYYY(brief.as_of_date)}
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`inline-flex items-center px-2.5 py-0.5 border rounded-full font-sans text-[11px] font-semibold ${regimePill}`}
          >
            {brief.regime_state}
          </span>
          <span
            className={`inline-flex items-center px-2.5 py-0.5 border rounded-full font-sans text-[11px] font-semibold capitalize ${summaryPill}`}
          >
            {brief.regime_summary}
          </span>
          {delta && (
            <span className={`font-sans text-[11px] font-medium ${delta.cls}`}>
              {delta.label}
            </span>
          )}
        </div>
      </header>

      <article className="font-serif text-[17px] leading-[1.6] text-ink-primary whitespace-pre-wrap">
        {brief.narrative}
      </article>

      {brief.key_themes && brief.key_themes.length > 0 && (
        <section className="mt-10">
          <h2 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-3">
            Key Themes
          </h2>
          <div className="flex flex-wrap gap-2">
            {brief.key_themes.map((theme, i) => (
              <span
                key={i}
                className="inline-flex items-center px-3 py-1 bg-paper-rule/30 border border-paper-rule rounded-sm font-sans text-xs text-ink-primary"
              >
                {theme}
              </span>
            ))}
          </div>
        </section>
      )}

      {brief.top_sector_mentions && brief.top_sector_mentions.length > 0 && (
        <section className="mt-8">
          <h2 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-3">
            Top Sector Mentions
          </h2>
          <div className="font-sans text-sm text-ink-secondary leading-relaxed">
            {brief.top_sector_mentions.join(' · ')}
          </div>
        </section>
      )}

      <footer className="mt-16 pt-6 border-t border-paper-rule">
        <div className="font-sans text-[11px] text-ink-tertiary leading-relaxed">
          <div>
            As of {fmtDDMMMYYYY(brief.as_of_date)} · generated{' '}
            {fmtTimestampIST(brief.generated_at)} IST
          </div>
          <div className="mt-1">
            Model {brief.model} · prompt {brief.prompt_version} · tokens{' '}
            {brief.input_tokens ?? '–'} in / {brief.output_tokens ?? '–'} out
          </div>
        </div>
      </footer>
    </main>
  )
}
