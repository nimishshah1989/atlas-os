// The Desk — plain-language view of the nightly AI trading cycle. Written for a
// reader who does not speak quant: money first, one plain sentence per action,
// jargon translated (no "alpha", "conviction 3/5", "R:R", "Jaccard"). Every
// number is journaled engine output from the desk_* tables — nothing derived.
import { getPendingOrders } from '@/lib/queries/desk'
import { getDeskCycles, getDeskIntel, type DeskCard, type DeskCycle } from '@/lib/queries/deskBoard'
import { DeskQueue } from '@/components/portfolios/DeskQueue'
import { Panel } from '@/components/ui/Panel'

const rupees = (v: number | null) =>
  v === null ? '—' : `₹${(v / 100000).toFixed(2)} lakh`

// what each desk is trying to do, in one plain sentence
const CHARTER_PLAIN: Record<string, string> = {
  sector_leaders: 'Backs the strongest stocks inside the strongest sectors.',
  conviction: 'Owns the market’s highest-conviction names, wherever they are.',
  quality_momentum: 'Only strong stocks that are also beating the market and trending up.',
  rotation: 'Tries to catch sectors early, as they turn from weak to strong.',
}

const confidenceWord = (c: number | null) =>
  c === null ? null : c >= 4 ? 'high confidence' : c === 3 ? 'medium confidence' : 'low confidence'

function money(v: number | null) {
  return v === null ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`
}

// one plain sentence summarising what the desk did tonight
function headline(d: DeskCycle): string {
  const sells = [...d.applied, ...d.queued].filter((c) => c.side === 'sell').length
  const buys = [...d.applied, ...d.queued].filter((c) => c.side === 'buy').length
  const queued = d.queued.length > 0
  if (sells + buys === 0) return 'No changes today — nothing looked worth acting on, so it held everything.'
  const parts: string[] = []
  if (buys) parts.push(`${buys} ${buys === 1 ? 'buy' : 'buys'}`)
  if (sells) parts.push(`${sells} ${sells === 1 ? 'sell' : 'sells'}`)
  const verb = queued ? 'proposed' : 'made'
  const tail = queued ? ' — waiting for your approval below' : ''
  return `Today it ${verb} ${parts.join(' and ')}${tail}.`
}

function ActionRow({ c }: { c: DeskCard }) {
  const bought = c.side === 'buy'
  const conf = confidenceWord(c.conviction)
  return (
    <li className="border-t border-edge-hair pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className={`font-num text-[12px] font-semibold ${bought ? 'text-pos' : 'text-neg'}`}>
          {bought ? 'BUY' : 'SELL'}
        </span>
        <span className="font-display text-[15px] font-medium text-txt-1">{c.symbol}</span>
        {bought && c.entryRef !== null && (
          <span className="font-num text-[13px] text-txt-2">around {money(c.entryRef)} a share</span>
        )}
        {conf && <span className="font-num text-[11px] text-txt-3">· {conf}</span>}
        {c.reduced && (
          <span className="font-num text-[11px] text-txt-3">· smaller-than-usual size (the reviewers were split)</span>
        )}
      </div>

      <p className="mt-1 font-sans text-[13px] text-txt-2">
        <span className="text-txt-3">Why: </span>
        {c.thesis}
      </p>

      {bought && c.stop !== null && c.target !== null && (
        <p className="mt-1 font-sans text-[13px] text-txt-2">
          <span className="text-txt-3">Safety net: </span>
          if it drops to <b className="font-num">{money(c.stop)}</b> the desk sells to cap the loss; it aims to
          take profit near <b className="font-num">{money(c.target)}</b>.
        </p>
      )}

      {c.invalidation && (
        <p className="mt-1 font-sans text-[13px] text-txt-2">
          <span className="text-txt-3">It will change its mind if: </span>
          {c.invalidation}
        </p>
      )}
    </li>
  )
}

function DeskCard_({ d }: { d: DeskCycle }) {
  const gain = d.nav !== null && d.startCapital !== null ? d.nav - d.startCapital : null
  const gainPct =
    gain !== null && d.startCapital ? (gain / d.startCapital) * 100 : null
  const actions = [...d.applied, ...d.queued]
  const shortName = d.name.replace('Atlas Desk — ', '')

  return (
    <Panel bodyClassName="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-[17px] font-medium text-txt-1">{shortName}</h3>
          <p className="mt-0.5 font-sans text-[12px] text-txt-3">
            {CHARTER_PLAIN[d.charter] ?? ''}
          </p>
        </div>
        <div className="text-right">
          <p className="font-num text-[17px] font-medium text-txt-1">{rupees(d.nav)}</p>
          <p className="font-num text-[11px] text-txt-3">
            {gain !== null && gainPct !== null ? (
              <>
                <span className={gain >= 0 ? 'text-pos' : 'text-neg'}>
                  {gain >= 0 ? '▲' : '▼'} {money(Math.abs(gain))} ({gainPct >= 0 ? '+' : ''}
                  {gainPct.toFixed(1)}%)
                </span>{' '}
                since it started with {rupees(d.startCapital)}
              </>
            ) : (
              'paper money'
            )}
          </p>
        </div>
      </div>

      <p className="mt-3 font-sans text-[13.5px] text-txt-1">{headline(d)}</p>

      {actions.length > 0 && (
        <ul className="mt-3 space-y-3">
          {actions.map((c) => (
            <ActionRow key={`${c.side}-${c.symbol}`} c={c} />
          ))}
        </ul>
      )}

      {d.proposals.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer font-sans text-[12px] text-txt-3 underline decoration-dotted underline-offset-2">
            What it looked at and decided against
          </summary>
          <ul className="mt-2 space-y-1.5">
            {d.proposals.map((p) => {
              const v = d.verdicts.find((x) => x.symbol === p.symbol)
              const acted = actions.some((c) => c.symbol === p.symbol)
              return (
                <li key={`${p.symbol}-${p.action}`} className="font-sans text-[12px] text-txt-2">
                  <b>{p.symbol}</b> — considered {p.action === 'add' ? 'buying' : p.action === 'exit' ? 'selling' : 'watching'};{' '}
                  {acted
                    ? 'went ahead.'
                    : v && v.verdict !== 'approve'
                      ? 'the risk reviewers said no, so it held off.'
                      : 'decided to wait.'}
                  {p.evidence[0] ? <span className="text-txt-3"> ({p.evidence[0]})</span> : null}
                </li>
              )
            })}
          </ul>
        </details>
      )}
    </Panel>
  )
}

const DESK_PLAIN: Record<string, string> = {
  Sector: 'sector',
  Charter: 'strategy',
  'Decision kind': 'buys vs sells',
}

export async function DeskBoardV1() {
  const [{ cycles, regime }, intel, pending] = await Promise.all([
    getDeskCycles(),
    getDeskIntel(),
    getPendingOrders(),
  ])
  // show the most telling track-record rows: by strategy and by sector, skip the internal "kind"
  const track = intel.credibility
    .filter((c) => c.dim === 'charter' || c.dim === 'sector')
    .filter((c) => c.n >= 5)
    .slice(0, 10)

  return (
    <div className="mx-auto max-w-[1200px] space-y-7 px-6 py-7">
      <div>
        <p className="font-num text-txt-3">Updated after each market close · market mood today: {regime ?? '—'}</p>
        <h1 className="font-display font-medium tracking-tight text-txt-1">Trading Desk</h1>
        <p className="mt-2 max-w-[760px] font-sans text-txt-2">
          Four AI-run model funds, each given <b>₹10 lakh of play money</b> (no real funds are
          connected). Every evening after the market closes, each one reviews Atlas’s scores and
          decides what to buy or sell — always with a built-in loss limit on each trade. This page
          shows exactly what each fund did and why.
        </p>
      </div>

      {pending.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-[15px] font-medium text-txt-1">Waiting for your decision</h2>
          <DeskQueue orders={pending} />
        </div>
      )}

      <div>
        <h2 className="mb-3 font-display text-[15px] font-medium text-txt-1">
          What each fund did {cycles[0] ? `· ${cycles[0].cycleDate}` : ''}
        </h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {cycles.map((d) => (
            <DeskCard_ key={d.portfolioId} d={d} />
          ))}
        </div>
      </div>

      {track.length > 0 && (
        <Panel
          eyebrow="Its report card"
          title="How good have the desk’s past calls been?"
          info={{
            body: 'Every buy and sell the desks have made, checked 20 trading days later against the overall market (NIFTY 500). “Beat the market” is the share of those calls that did better than simply holding the index. “Average edge” is how much better, on average — a positive number means the desk added value.',
          }}
          bodyClassName="px-5 py-3"
        >
          <table className="w-full font-num text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.1em] text-txt-3">
                <th className="py-1.5 font-normal">Grouped by</th>
                <th className="py-1.5 text-right font-normal">Calls made</th>
                <th className="py-1.5 text-right font-normal">Beat the market</th>
                <th className="py-1.5 text-right font-normal">Average edge</th>
              </tr>
            </thead>
            <tbody className="text-txt-2">
              {track.map((c) => (
                <tr key={`${c.dim}-${c.dimValue}`} className="border-t border-edge-hair">
                  <td className="py-1.5">
                    <span className="text-txt-3">{DESK_PLAIN[c.dim === 'charter' ? 'Charter' : 'Sector']}: </span>
                    {c.dimValue.replace('_', ' ')}
                  </td>
                  <td className="py-1.5 text-right">{c.n}</td>
                  <td className="py-1.5 text-right">{(c.hitRate * 100).toFixed(0)}%</td>
                  <td className={`py-1.5 text-right ${c.avgAlpha >= 0 ? 'text-pos' : 'text-neg'}`}>
                    {c.avgAlpha >= 0 ? '+' : ''}
                    {c.avgAlpha.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <details className="rounded-panel border border-edge-hair bg-surface-panel px-5 py-4">
        <summary className="cursor-pointer font-display text-[15px] font-medium text-txt-1">
          Under the hood — how the desk learns and stays honest
        </summary>
        <div className="mt-4 space-y-5">
          {intel.lessons.length > 0 && (
            <div>
              <p className="mb-1.5 font-num text-[11px] uppercase tracking-[0.12em] text-txt-3">
                What it has learned from its own results
              </p>
              <ul className="space-y-1.5">
                {intel.lessons.slice(0, 5).map((l) => (
                  <li key={l.lesson.slice(0, 50)} className="font-sans text-[13px] text-txt-2">
                    • {l.lesson.split(' [basis:')[0]}
                    <span className="font-num text-[11px] text-txt-3">
                      {' '}
                      ({l.desk.replace('Atlas Desk — ', '')}, confidence {(l.confidence * 100).toFixed(0)}%)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {intel.audits.length > 0 && (
            <div>
              <p className="mb-1.5 font-num text-[11px] uppercase tracking-[0.12em] text-txt-3">
                Honesty check: is it trading on data, or on famous names?
              </p>
              <p className="font-sans text-[13px] text-txt-2">
                Each week we hide the company names and ask a desk to pick again. If it makes the same
                picks, it’s reacting to the numbers, not to brand familiarity.
              </p>
              <ul className="mt-1.5">
                {intel.audits.slice(0, 3).map((a) => (
                  <li key={a.ts + a.desk} className="font-num text-[12px] text-txt-2">
                    {a.ts} · {a.desk.replace('Atlas Desk — ', '')}: {(a.jaccard * 100).toFixed(0)}% of picks
                    stayed the same with names hidden
                  </li>
                ))}
              </ul>
            </div>
          )}

          {intel.alerts.length > 0 && (
            <div>
              <p className="mb-1.5 font-num text-[11px] uppercase tracking-[0.12em] text-txt-3">
                Recent price alerts
              </p>
              <ul>
                {intel.alerts.slice(0, 5).map((a) => (
                  <li key={a.date + a.symbol + a.kind} className="font-sans text-[13px] text-txt-2">
                    {a.date} · {a.symbol} {a.kind === 'stop' ? 'hit its loss limit' : 'reached its profit target'} (₹
                    {Math.round(a.level).toLocaleString('en-IN')})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>
    </div>
  )
}
