// src/app/themes/page.tsx — what the funds are actually about, and which of those things is working.
import { ThemeGrid } from '@/components/themes/ThemeGrid'
import { EodStamp } from '@/components/ui/EodStamp'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { getThemes } from '@/lib/queries/themes'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Themes' }

export default async function ThemesPage() {
  await requireUser()
  const list = await attempt(getThemes())
  return (
    <div className="page">
      <PageHeader
        title="Themes"
        lead="What a fund is about — AI, uranium, gold miners, water — with the strongest fund in each. Click a theme."
        aside={list.ok && list.value.date ? <EodStamp eod={list.value.date} asOf={list.value.date} /> : undefined}
      />
      {list.ok ? <ThemeGrid list={list.value} /> : <QueryFailed error={list.error} />}
      <p className="mt-4 max-w-(--measure) text-meta text-ink-3">
        A fund carries up to three themes and counts in each. Figures are the MEDIAN member, not a
        weighted mean, so one giant fund cannot stand for its theme.
      </p>
    </div>
  )
}
