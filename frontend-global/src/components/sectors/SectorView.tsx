// SectorView — one sector's page: how it has been doing, the themes inside it, and both sides of
// what you can own — the funds under each theme, and the S&P 500 companies filed under the sector.
//
// The FM: "we have a sector page… double-clicking on sectors will get us to drill down from there.
// We can have much better representations of sectors at the theme level: different visuals,
// bubble charts, line charts, historic data, and how these sectors have been doing. When you
// double-click on sectors, you have both stocks and ETFs coming into play."
//
// ONE COMPONENT DRAWS THE THEMES, and it is the SAME one /sectors draws sectors with. The columns,
// the tints, the sort and the expand behaviour are therefore identical by construction rather than
// by anyone remembering — which is the consistency this board was short of.
import { EodStamp } from '@/components/ui/EodStamp'
import { InfoTip } from '@/components/ui/InfoTip'
import { PageHeader } from '@/components/ui/PageHeader'
import { Section } from '@/components/ui/Section'
import { StatCard } from '@/components/ui/StatCard'
import { formatDecimal, formatIsoDate, formatPct, formatUsdCompact } from '@/lib/format'
import { rsTint } from '@/lib/scores'
import { SECTOR_WINDOWS, type SectorDetail } from '@/lib/sectors'
import { SectorHeatmap } from './SectorHeatmap'
import { SectorStockTable } from './SectorStockTable'
import { SectorTrend } from './SectorTrend'
import { Unscored } from './Unscored'

const WINDOW_LABEL: Record<(typeof SECTOR_WINDOWS)[number], string> = {
  '3m': '3 months',
  '6m': '6 months',
  '12m': '1 year',
}

export function SectorView({ detail }: { detail: SectorDetail }) {
  const { node, date, stocks, history, history_from } = detail
  const scoredStocks = stocks.filter((s) => s.composite != null).length

  return (
    <div className="page">
      <PageHeader
        title={node.name}
        lead={
          node.n_scored === 0
            ? 'No fund under this sector is scored yet.'
            : `${node.n_children} ${node.n_children === 1 ? 'theme' : 'themes'}, ${node.n_scored} scored ${
                node.n_scored === 1 ? 'fund' : 'funds'
              }${scoredStocks > 0 ? `, and ${scoredStocks} scored S&P 500 members` : ''}.`
        }
        aside={date ? <EodStamp eod={date} asOf={date} /> : undefined}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Median fund score"
          value={node.composite == null ? '—' : formatDecimal(node.composite, 0)}
          sub={
            node.rank == null
              ? 'nothing scored here yet'
              : `${node.rank} of ${node.n_ranked} sectors`
          }
        />
        <StatCard
          label="Above 200-day"
          value={node.above_ema200_frac == null ? '—' : formatPct(node.above_ema200_frac, 0)}
          sub="of the sector's measured funds"
        />
        <StatCard label="Themes" value={node.n_children} sub={`over ${node.n_funds} classified funds`} />
        <StatCard label="Assets" value={formatUsdCompact(node.aum_usd)} sub="in its themed funds" />
      </div>

      <Section
        title="Against the S&P 500"
        note="median member fund, (1+r)/(1+r SPY) − 1"
      >
        <div className="panel flex flex-wrap gap-px overflow-hidden">
          {SECTOR_WINDOWS.map((w) => (
            <div key={w} className="min-w-[110px] flex-1 px-3 py-2" style={{ background: rsTint(node.rs[w]) }}>
              <div className="font-num text-[9.5px] uppercase tracking-[0.1em] text-ink-3">
                {WINDOW_LABEL[w]}
              </div>
              <div className="font-display text-[17px] font-semibold tabular-nums text-ink">
                {node.rs[w] == null ? '—' : formatPct(node.rs[w], 1, { sign: true })}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {history.length > 1 && (
        <Section
          title="How the sector has been doing"
          note={history_from ? `since ${formatIsoDate(history_from)}, rebased to 100` : 'rebased to 100'}
        >
          <div className="panel px-3 py-3">
            <SectorTrend name={node.name} points={history} />
            <p className="mt-1 text-meta text-ink-3">
              The MEDIAN member fund&apos;s total return, each rebased to its own close on the first
              session shown, against the S&amp;P over the same sessions.{' '}
              <InfoTip title="What this line leaves out">
                Membership is fixed at the start of the window, so a fund listed since is not in
                this line and one that closed is not either. A chained index over changing
                membership is a producer&apos;s job, not a page&apos;s — this board does not invent
                one.
              </InfoTip>
            </p>
          </div>
        </Section>
      )}

      <Section
        title="Themes in this sector"
        note="open a theme to see its funds ranked against each other"
      >
        <SectorHeatmap
          tree={{ date, rows: node.children, n_unthemed: 0 }}
          heading="Theme · fund"
          emptyNote="No theme under this sector has a classified fund yet."
        />
        <Unscored node={node} />
      </Section>

      <Section title="S&P 500 members" note="filed under this sector by the SPDR holdings file">
        <SectorStockTable rows={stocks} />
      </Section>
    </div>
  )
}
