// frontend/src/components/regime/TodayWorklist.tsx
// 3-count worklist: sectors entered favour / fresh breakouts / deteriorating holdings.
// Clickable counts. Pure presentational.
//
// 2026-05-29: removed inline "Fresh Breakouts" + "Review/Trim" symbol lists.
// They duplicated the "Top conviction" table at the bottom of the page (same
// names showed up in both). Worklist now stays as 3 numeric KPIs at the top
// and the conviction table owns the full per-symbol grid.
import Link from 'next/link'

export type WorklistData = {
  sectorsEnteredFavour: number
  freshBreakouts: number
  breakoutSymbols: string[]
  deterioratingCount: number
  deterioratingSymbols: string[]
}

type CountCardProps = {
  count: number
  label: string
  linkHref: string
  linkTestId: string
  sublabel?: string
}

function CountCard({ count, label, linkHref, linkTestId, sublabel }: CountCardProps) {
  return (
    <Link
      href={linkHref}
      data-testid={linkTestId}
      className="flex flex-col gap-1 border border-paper-rule rounded-sm px-4 py-3 hover:border-teal/40 hover:bg-teal/5 transition-colors group"
    >
      <span className="font-mono text-3xl font-semibold text-ink-primary group-hover:text-teal tabular-nums leading-none">
        {count}
      </span>
      <span className="font-sans text-xs text-ink-secondary leading-snug">{label}</span>
      {sublabel && (
        <span className="font-sans text-[10px] text-ink-tertiary">{sublabel}</span>
      )}
    </Link>
  )
}

type Props = {
  data: WorklistData
}

export function TodayWorklist({ data }: Props) {
  const breakoutHref =
    data.breakoutSymbols.length > 0
      ? `/stocks/${encodeURIComponent(data.breakoutSymbols[0])}`
      : '/stocks'

  return (
    <div className="px-6 py-4 border-b border-paper-rule">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3">
        Today&apos;s Worklist
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <CountCard
          count={data.sectorsEnteredFavour}
          label="sectors entered favour"
          linkHref="/sectors"
          linkTestId="worklist-sectors-link"
          sublabel="new Overweight signals"
        />
        <CountCard
          count={data.freshBreakouts}
          label="fresh breakouts"
          linkHref={breakoutHref}
          linkTestId="worklist-breakout-link"
          sublabel="stage 2 entries today"
        />
        <div className="flex flex-col gap-1 border border-paper-rule rounded-sm px-4 py-3">
          <span className="font-mono text-3xl font-semibold text-ink-primary tabular-nums leading-none">
            {data.deterioratingCount}
          </span>
          <span className="font-sans text-xs text-ink-secondary leading-snug">
            holdings deteriorating
          </span>
          <span className="font-sans text-[10px] text-ink-tertiary">stage 3/4 transitions</span>
        </div>
      </div>

    </div>
  )
}
