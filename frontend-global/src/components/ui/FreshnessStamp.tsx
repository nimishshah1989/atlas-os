// src/components/ui/FreshnessStamp.tsx — "As of Thu 3 Sep 2026, 21:00 ET" with a dot: green when
// the latest successful pipeline step is recent, amber when it is stale (and the copy says so),
// grey when there is nothing to date. Every surface carries one (design principle 5).
import { connection } from 'next/server'
import { formatAge, formatAsOf } from '@/lib/format'
import { getFreshness, type Freshness } from '@/lib/queries/health'

type Tone = 'green' | 'amber' | 'grey'

const DOT: Record<Tone, string> = { green: 'bg-pos', amber: 'bg-warn', grey: 'bg-ink-3' }

export function describeFreshness(f: Freshness): { tone: Tone; text: string } {
  switch (f.state) {
    case 'no-db':
      return { tone: 'grey', text: 'No database configured' }
    case 'none':
      return { tone: 'grey', text: 'No pipeline run yet' }
    case 'error':
      return { tone: 'grey', text: 'Freshness unknown: the database did not answer' }
    case 'fresh':
      return { tone: 'green', text: `As of ${formatAsOf(f.ended_at)}` }
    case 'stale':
      return { tone: 'amber', text: `As of ${formatAsOf(f.ended_at)}, stale (last run ${formatAge(f.age_hours)})` }
  }
}

export async function FreshnessStamp({ size = 'sm' }: { size?: 'sm' | 'lg' }) {
  // Render per request, never at build: the stamp must not bake into a static shell.
  await connection()
  let f: Freshness
  try {
    f = await getFreshness()
  } catch (e) {
    f = { state: 'error', error: e instanceof Error ? e.message : String(e) }
  }
  const { tone, text } = describeFreshness(f)
  return (
    <span
      className={`inline-flex items-center gap-2 text-ink-2 ${size === 'lg' ? 'text-body' : 'text-meta'}`}
      data-freshness={f.state}
    >
      <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${DOT[tone]}`} />
      <span>{text}</span>
    </span>
  )
}
