// The Desk — glass-box board for the nightly agent trading cycle. Everything
// rendered here is journaled engine output: scout proposals, 3-stance risk
// consensus, PM orders with code-verified trade plans, bookings/queue, and the
// desk's measured track record. Server component; approval actions live in the
// (client) DeskQueue.
import { getPendingOrders } from '@/lib/queries/desk'
import { getDeskCycles, getDeskIntel, type DeskCard, type DeskCycle } from '@/lib/queries/deskBoard'
import { DeskQueue } from '@/components/portfolios/DeskQueue'
import { Panel } from '@/components/ui/Panel'

const inr = (v: number | null) =>
  v === null ? '—' : `₹${(v / 100000).toFixed(2)}L`

function Chip({ tone, children }: { tone: 'pos' | 'neg' | 'mut'; children: React.ReactNode }) {
  const color =
    tone === 'pos' ? 'text-pos' : tone === 'neg' ? 'text-neg' : 'text-txt-3'
  return (
    <span className={`rounded-md border border-edge-hair px-1.5 py-0.5 font-num text-[10px] uppercase tracking-[0.1em] ${color}`}>
      {children}
    </span>
  )
}

function Card({ c, tag }: { c: DeskCard; tag: string }) {
  return (
    <li className="rounded-lg border border-edge-hair px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Chip tone={c.side === 'buy' ? 'pos' : 'neg'}>{c.side}</Chip>
        <span className="font-display text-[15px] font-medium text-txt-1">{c.symbol}</span>
        <span className="font-num text-[11px] text-txt-3">{tag}</span>
        {c.conviction !== null && (
          <span className="font-num text-[11px] text-txt-3">conviction {c.conviction}/5</span>
        )}
        {c.reduced && <Chip tone="mut">half size · split vote</Chip>}
        {c.stop !== null && (
          <span className="ml-auto font-num text-[12px] text-txt-2">
            entry {c.entryRef} · stop {c.stop} · target {c.target} · R:R {c.rr}
          </span>
        )}
      </div>
      <p className="mt-1 font-sans text-[13px] text-txt-2">{c.thesis}</p>
      <p className="mt-0.5 font-sans text-[12px] text-txt-3">Exit if: {c.invalidation}</p>
      {c.planBasis && (
        <p className="mt-0.5 font-num text-[11px] text-txt-3">levels: {c.planBasis}</p>
      )}
    </li>
  )
}

function CycleCard({ d }: { d: DeskCycle }) {
  const acted = d.applied.length + d.queued.length > 0
  return (
    <Panel
      eyebrow={`cycle ${d.cycleDate} · ${d.charter.replace('_', ' ')}`}
      title={d.name.replace('Atlas Desk — ', '')}
      action={
        <span className="flex items-center gap-2">
          {d.cvar && d.cvar.state === 'derisk' && <Chip tone="neg">de-risk</Chip>}
          <span className="font-num text-[12px] text-txt-2">{inr(d.nav)} paper NAV</span>
        </span>
      }
      bodyClassName="px-5 py-4"
    >
      {acted ? (
        <ul className="space-y-2.5">
          {d.applied.map((c) => (
            <Card key={`a-${c.symbol}`} c={c} tag={c.price !== null ? `booked @ ${c.price}` : 'booked'} />
          ))}
          {d.queued.map((c) => (
            <Card key={`q-${c.symbol}`} c={c} tag="awaiting your approval" />
          ))}
        </ul>
      ) : (
        <p className="font-sans text-[13px] text-txt-3">
          No action — {d.pmNote ?? d.errors[0] ?? 'nothing material changed; holding is a decision.'}
        </p>
      )}

      {(d.proposals.length > 0 || d.verdicts.length > 0) && (
        <details className="mt-3">
          <summary className="cursor-pointer font-num text-[11px] uppercase tracking-[0.12em] text-txt-3">
            Full reasoning — scout &amp; risk votes
          </summary>
          <div className="mt-2 space-y-2">
            {d.proposals.map((p) => (
              <div key={`p-${p.symbol}-${p.action}`} className="rounded-lg border border-edge-hair px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip tone={p.action === 'add' ? 'pos' : p.action === 'exit' ? 'neg' : 'mut'}>{p.action}</Chip>
                  <span className="font-display text-[13px] text-txt-1">{p.symbol}</span>
                  <span className="font-num text-[11px] text-txt-3">
                    urgency {p.urgency}
                    {p.conviction !== null ? ` · conviction ${p.conviction}/5` : ''}
                  </span>
                  {(() => {
                    const v = d.verdicts.find((x) => x.symbol === p.symbol)
                    return v ? (
                      <span className="ml-auto font-num text-[11px] text-txt-2">
                        risk: {v.verdict}
                        {v.consensus !== null ? ` (${v.consensus}/3 stances)` : ''}
                      </span>
                    ) : null
                  })()}
                </div>
                <ul className="mt-1 list-disc pl-5 font-sans text-[12px] text-txt-3">
                  {p.evidence.slice(0, 3).map((e) => (
                    <li key={e.slice(0, 40)}>{e}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}
      {d.errors.length > 0 && acted && (
        <p className="mt-2 font-num text-[11px] text-txt-3">⚠ {d.errors.length} filtered/errors journaled</p>
      )}
    </Panel>
  )
}

const DIM_LABEL: Record<string, string> = {
  desk: 'Desk',
  charter: 'Charter',
  sector: 'Sector',
  kind: 'Decision kind',
}

export async function DeskBoardV1() {
  const [{ cycles, regime }, intel, pending] = await Promise.all([
    getDeskCycles(),
    getDeskIntel(),
    getPendingOrders(),
  ])
  const cred = intel.credibility.filter((c) => c.dim !== 'desk')
  return (
    <div className="mx-auto max-w-[1400px] space-y-7 px-6 py-7">
      <div>
        <p className="font-num text-txt-3">
          Paper-traded agent desk · regime {regime ?? '—'} · latest cycle{' '}
          {cycles[0]?.cycleDate ?? '—'}
        </p>
        <h1 className="font-display font-medium tracking-tight text-txt-1">The Desk</h1>
        <p className="mt-2 max-w-[900px] font-sans text-txt-2">
          Every evening after close, four AI desks scan Atlas&apos;s scores, debate risk from
          three stances, and issue orders with code-enforced stops, targets and position
          caps — on paper money, journaled in full. This page is that journal.
        </p>
      </div>

      <DeskQueue orders={pending} />

      <div className="grid gap-4 lg:grid-cols-2">
        {cycles.map((d) => (
          <CycleCard key={d.portfolioId} d={d} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel
          eyebrow="Measured, not claimed"
          title="Track record by pocket"
          info={{
            body: 'Rolling hit-rate and average alpha vs NIFTY 500 of every stamped desk decision, grouped by charter, sector and decision kind. The PM sees these numbers before every order.',
          }}
          bodyClassName="px-5 py-3"
        >
          <table className="w-full font-num text-[12px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-[0.12em] text-txt-3">
                <th className="py-1 font-normal">Pocket</th>
                <th className="py-1 text-right font-normal">n</th>
                <th className="py-1 text-right font-normal">hit</th>
                <th className="py-1 text-right font-normal">α</th>
              </tr>
            </thead>
            <tbody className="text-txt-2">
              {cred.slice(0, 12).map((c) => (
                <tr key={`${c.dim}-${c.dimValue}`} className="border-t border-edge-hair">
                  <td className="py-1">
                    <span className="text-txt-3">{DIM_LABEL[c.dim] ?? c.dim} · </span>
                    {c.dimValue.replace('_', ' ')}
                  </td>
                  <td className="py-1 text-right">{c.n}</td>
                  <td className="py-1 text-right">{(c.hitRate * 100).toFixed(0)}%</td>
                  <td className={`py-1 text-right ${c.avgAlpha >= 0 ? 'text-pos' : 'text-neg'}`}>
                    {c.avgAlpha.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel
          eyebrow="Earned, decaying memory"
          title="Lessons the desk believes"
          info={{
            body: 'Written weekly by reflecting on stamped outcomes. Confidence rises when later results confirm a lesson and decays when they don’t — fast-layer lessons fade in weeks, slow-layer principles persist. Contrast lessons come from comparing the best and worst realized calls.',
          }}
          bodyClassName="px-5 py-3"
        >
          <ul className="space-y-2">
            {intel.lessons.slice(0, 6).map((l) => (
              <li key={l.lesson.slice(0, 50)} className="border-t border-edge-hair pt-2 first:border-t-0 first:pt-0">
                <div className="flex items-center gap-2">
                  <Chip tone="mut">{l.layer}</Chip>
                  {l.contrast && <Chip tone="mut">contrast</Chip>}
                  <span className="font-num text-[11px] text-txt-3">
                    {l.desk.replace('Atlas Desk — ', '')} · conf {l.confidence.toFixed(2)}
                  </span>
                </div>
                <p className="mt-1 font-sans text-[12px] text-txt-2">{l.lesson.split(' [basis:')[0]}</p>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          eyebrow="The desk questions itself"
          title="Research &amp; audits"
          info={{
            body: 'Weekly: a falsifiable hypothesis about the desk’s own rules, evaluated against its realized decisions; and a masked-ticker audit — the scout re-run with anonymized names. Low overlap means name familiarity, not data, drove the picks.',
          }}
          bodyClassName="px-5 py-3"
        >
          <div className="space-y-3">
            {intel.hypotheses.slice(0, 2).map((h) => (
              <div key={h.ts + h.thresholdKey}>
                <p className="font-num text-[11px] uppercase tracking-[0.1em] text-txt-3">
                  hypothesis · {h.ts} · {h.verdict.replace('_', ' ')}
                </p>
                <p className="font-sans text-[12px] text-txt-2">
                  {h.hypothesis} <span className="font-num text-txt-3">({h.thresholdKey} → {h.proposedValue})</span>
                </p>
              </div>
            ))}
            <div>
              <p className="font-num text-[11px] uppercase tracking-[0.1em] text-txt-3">
                masked-ticker audit (1.0 = data-driven)
              </p>
              {intel.audits.map((a) => (
                <p key={a.ts + a.desk} className="font-num text-[12px] text-txt-2">
                  {a.ts} · {a.desk.replace('Atlas Desk — ', '')} · overlap {a.jaccard.toFixed(2)}
                </p>
              ))}
            </div>
            {intel.alerts.length > 0 && (
              <div>
                <p className="font-num text-[11px] uppercase tracking-[0.1em] text-txt-3">
                  intraday breach alerts
                </p>
                {intel.alerts.slice(0, 5).map((a) => (
                  <p key={a.date + a.symbol + a.kind} className="font-num text-[12px] text-txt-2">
                    {a.date} · {a.symbol} {a.kind === 'stop' ? '🛑 stop' : '🎯 target'} {a.level} (quote {a.quote})
                  </p>
                ))}
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}
