// The Desk overview — all four AI-run funds side by side, in plain language.
// Each card links through to that fund's full history on its portfolio page.
// Shares DeskCycleBody / DeskReportCard with the detail page so they never drift.
import Link from 'next/link'

import { getPendingOrders } from '@/lib/queries/desk'
import { getDeskCycles, getDeskIntel } from '@/lib/queries/deskBoard'
import { DeskCycleBody, DeskReportCard } from '@/components/desk/DeskCyclePlain'
import { DeskQueue } from '@/components/portfolios/DeskQueue'
import { Panel } from '@/components/ui/Panel'

export async function DeskBoardV1() {
  const [{ cycles, regime }, intel, pending] = await Promise.all([
    getDeskCycles(),
    getDeskIntel(),
    getPendingOrders(),
  ])
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
          decides what to buy or sell — always with a built-in loss limit on each trade. Click any
          fund to see its full history.
        </p>
      </div>

      {pending.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-[15px] font-medium text-txt-1">Waiting for your decision</h2>
          <DeskQueue orders={pending} />
        </div>
      )}

      <div>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-[15px] font-medium text-txt-1">
            What each fund did {cycles[0] ? `· ${cycles[0].cycleDate}` : ''}
          </h2>
          <Link href="/desk/engine-room" className="font-sans text-[12px] text-accent no-underline hover:underline">
            Engine Room — replay a night, agent by agent →
          </Link>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {cycles.map((d) => (
            <Panel key={d.portfolioId} bodyClassName="px-5 py-4">
              <DeskCycleBody cycle={d} detailHref={`/portfolios/${d.portfolioId}`} />
            </Panel>
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
          <DeskReportCard track={track} />
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
              <p className="mb-1.5 font-num text-[11px] uppercase tracking-[0.12em] text-txt-3">Recent price alerts</p>
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
