// The Engine Room — replay one desk's decision relay for one night, stage by
// stage: Scout → Risk (3 stances) → Debate → PM → Trader → Booked. URL-driven
// (?desk=&date=) so it's a pure server component; navigation is plain links,
// expansions are native <details>. Every line is journaled agent output.
import Link from 'next/link'

import { getDeskCycleTrace, type DeskCard } from '@/lib/queries/deskBoard'
import { CHARTER_PLAIN } from '@/components/desk/DeskCyclePlain'

const money = (v: number | null) => (v === null ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`)
const conf = (c: number | null) => (c === null ? '' : ` · confidence ${c}/5`)
const short = (n: string) => n.replace('Atlas Desk — ', '')

const VERDICT_MARK: Record<string, string> = { approve: '✓', veto: '✗', defer: '~' }
const VERDICT_TONE: Record<string, string> = {
  approve: 'text-sig-pos',
  veto: 'text-sig-neg',
  defer: 'text-sig-warn',
}

function Stage({ n, title, agent, children }: { n: number; title: string; agent: string; children: React.ReactNode }) {
  return (
    <div className="relative border-l-2 border-edge-hair pl-6">
      <span className="absolute -left-[13px] top-0 flex h-6 w-6 items-center justify-center rounded-full border border-edge-strong bg-surface-panel font-num text-[11px] text-txt-2">
        {n}
      </span>
      <div className="pb-6">
        <div className="flex items-baseline gap-2">
          <h3 className="font-display text-[15px] font-medium text-txt-1">{title}</h3>
          <span className="font-num text-[10px] uppercase tracking-[0.12em] text-txt-3">{agent}</span>
        </div>
        <div className="mt-2">{children}</div>
      </div>
    </div>
  )
}

function empty(msg: string) {
  return <p className="font-sans text-[13px] text-txt-3">{msg}</p>
}

function bookedRow(c: DeskCard, tag: string) {
  return (
    <li key={`${c.side}-${c.symbol}`} className="font-sans text-[13px] text-txt-2">
      <span className={`font-num text-[11px] font-semibold ${c.side === 'buy' ? 'text-sig-pos' : 'text-sig-neg'}`}>
        {c.side.toUpperCase()}
      </span>{' '}
      <b>{c.symbol}</b> {c.price !== null ? `@ ${money(c.price)}` : ''} <span className="text-txt-3">· {tag}</span>
      {c.reduced ? <span className="text-txt-3"> (half size — split vote)</span> : null}
    </li>
  )
}

export async function EngineRoom({ desk, date }: { desk?: string; date?: string }) {
  const t = await getDeskCycleTrace(desk, date)
  if (t.desks.length === 0) return <div className="px-6 py-7 font-sans text-txt-3">No desks yet.</div>

  const cur = t.desks.find((d) => d.id === (desk ?? t.desks[0].id)) ?? t.desks[0]
  const di = t.dates.indexOf(t.cycleDate ?? '')
  const prevDate = di >= 0 && di < t.dates.length - 1 ? t.dates[di + 1] : null // dates newest-first
  const nextDate = di > 0 ? t.dates[di - 1] : null
  const q = (id: string, d?: string | null) => `/desk/engine-room?desk=${id}${d ? `&date=${d}` : ''}`
  const stanceFor = (name: string, sym: string) => t.stances.find((s) => s.name === name)?.votes.find((v) => v.symbol === sym)

  return (
    <div className="mx-auto max-w-[1000px] space-y-6 px-6 py-7">
      <div>
        <p className="font-num text-txt-3">
          <Link href="/desk" className="text-accent no-underline hover:underline">The Desk</Link> · Engine Room
        </p>
        <h1 className="font-display font-medium tracking-tight text-txt-1">Watch the agents work</h1>
        <p className="mt-2 max-w-[720px] font-sans text-txt-2">
          Replay any evening’s decision, stage by stage — what each agent saw, decided, and why,
          including the ideas that were vetoed or filtered out before any trade.
        </p>
      </div>

      {/* desk tabs */}
      <div className="flex flex-wrap gap-1.5">
        {t.desks.map((d) => (
          <Link
            key={d.id}
            href={q(d.id)}
            className={`rounded-tile border px-3 py-1 font-sans text-[12px] no-underline ${
              d.id === cur.id
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-edge-hair text-txt-2 hover:border-edge-strong'
            }`}
          >
            {short(d.name)}
          </Link>
        ))}
      </div>

      {/* night picker */}
      <div className="flex items-center justify-between rounded-panel border border-edge-hair bg-surface-panel px-4 py-2.5">
        <div>
          <p className="font-num text-[11px] uppercase tracking-[0.12em] text-txt-3">{CHARTER_PLAIN[cur.charter] ?? ''}</p>
          <p className="font-display text-[15px] font-medium text-txt-1">
            {short(cur.name)} · {t.cycleDate ?? '—'}
          </p>
        </div>
        <div className="flex items-center gap-2 font-num text-[12px]">
          {t.regime && <span className="text-txt-3">market: {t.regime}</span>}
          {t.cvar?.state === 'derisk' && (
            <span className="rounded-tile border border-sig-neg/30 bg-sig-neg/10 px-2 py-0.5 text-sig-neg">de-risk</span>
          )}
          {prevDate ? (
            <Link href={q(cur.id, prevDate)} className="text-accent no-underline hover:underline">← earlier</Link>
          ) : (
            <span className="text-txt-3">← earlier</span>
          )}
          {nextDate ? (
            <Link href={q(cur.id, nextDate)} className="text-accent no-underline hover:underline">later →</Link>
          ) : (
            <span className="text-txt-3">later →</span>
          )}
        </div>
      </div>

      {/* the relay */}
      <div>
        <Stage n={1} title="Scanned the market" agent="Scout">
          {t.scout.length === 0
            ? empty(t.scoutNote ?? 'Nothing changed materially — flagged nothing.')
            : (
              <ul className="space-y-2">
                {t.scout.map((p) => (
                  <li key={`${p.symbol}-${p.action}`} className="font-sans text-[13px] text-txt-2">
                    <b>{p.symbol}</b> — worth {p.action === 'add' ? 'buying' : p.action === 'exit' ? 'selling' : 'watching'}
                    <span className="text-txt-3">{conf(p.conviction)}{p.urgency === 'high' ? ' · urgent' : ''}</span>
                    {p.evidence[0] && <span className="text-txt-3"> — {p.evidence.join('; ')}</span>}
                  </li>
                ))}
              </ul>
            )}
        </Stage>

        <Stage n={2} title="Risk reviewed it — three views" agent="Safe · Neutral · Risky">
          {t.verdicts.length === 0
            ? empty('No proposals reached the risk desk.')
            : (
              <ul className="space-y-2">
                {t.verdicts.map((v) => (
                  <li key={v.symbol} className="font-sans text-[13px] text-txt-2">
                    <b>{v.symbol}</b>{' '}
                    {['SAFE', 'NEUTRAL', 'RISKY'].map((nm) => {
                      const sv = stanceFor(nm.toLowerCase(), v.symbol)
                      const vv = sv?.verdict ?? ''
                      return (
                        <span key={nm} className="font-num text-[11px] text-txt-3">
                          {nm[0]}
                          <span className={VERDICT_TONE[vv] ?? 'text-txt-3'}>{VERDICT_MARK[vv] ?? '·'}</span>{' '}
                        </span>
                      )
                    })}
                    <span className={`font-num text-[12px] ${VERDICT_TONE[v.verdict] ?? ''}`}>
                      → {v.verdict}{v.consensus !== null ? ` (${v.consensus}/3)` : ''}
                      {v.reduced ? ', half size' : ''}
                    </span>
                    {v.reason && (
                      <details className="mt-0.5">
                        <summary className="cursor-pointer font-sans text-[11px] text-txt-3 underline decoration-dotted underline-offset-2">
                          why each reviewer voted that way
                        </summary>
                        <p className="mt-1 font-sans text-[12px] text-txt-3">{v.reason}</p>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            )}
        </Stage>

        {t.debates.length > 0 && (
          <Stage n={3} title="They argued it out" agent="Bull vs Bear">
            <div className="space-y-2">
              {t.debates.map((d) => (
                <details key={d.symbol} className="rounded-tile border border-edge-hair px-3 py-2">
                  <summary className="cursor-pointer font-sans text-[13px] text-txt-2">
                    <b>{d.symbol}</b> — the contested call
                  </summary>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    <div>
                      <p className="font-num text-[10px] uppercase tracking-wider text-sig-pos">Bull</p>
                      <ul className="list-disc pl-4 font-sans text-[12px] text-txt-2">
                        {(d.bull?.points ?? []).map((p) => <li key={p.slice(0, 30)}>{p}</li>)}
                      </ul>
                    </div>
                    <div>
                      <p className="font-num text-[10px] uppercase tracking-wider text-sig-neg">Bear</p>
                      <ul className="list-disc pl-4 font-sans text-[12px] text-txt-2">
                        {(d.bear?.points ?? []).map((p) => <li key={p.slice(0, 30)}>{p}</li>)}
                      </ul>
                    </div>
                  </div>
                </details>
              ))}
            </div>
          </Stage>
        )}

        <Stage n={t.debates.length > 0 ? 4 : 3} title="The manager decided" agent="Portfolio Manager">
          {t.pmOrders.length === 0
            ? empty(t.pmNote ?? 'Placed no orders.')
            : (
              <ul className="space-y-2">
                {t.pmOrders.map((o) => (
                  <li key={`${o.side}-${o.symbol}`} className="font-sans text-[13px] text-txt-2">
                    <span className={`font-num text-[11px] font-semibold ${o.side === 'buy' ? 'text-sig-pos' : 'text-sig-neg'}`}>
                      {o.side.toUpperCase()}
                    </span>{' '}
                    <b>{o.symbol}</b><span className="text-txt-3">{conf(o.conviction)}</span>
                    <br />
                    <span className="text-txt-3">Why: </span>{o.thesis}
                    <br />
                    <span className="text-txt-3">Exit if: </span>{o.invalidation}
                  </li>
                ))}
              </ul>
            )}
        </Stage>

        {t.traderPlans.length > 0 && (
          <Stage n={t.debates.length > 0 ? 5 : 4} title="Set the exit levels" agent="Execution Trader">
            <ul className="space-y-1.5">
              {t.traderPlans.map((p) => (
                <li key={p.symbol} className="font-sans text-[13px] text-txt-2">
                  <b>{p.symbol}</b> — sell to cap loss at <b className="font-num">{money(p.stop)}</b>, aim for{' '}
                  <b className="font-num">{money(p.target)}</b>
                  {p.rr !== null && <span className="text-txt-3"> (about {p.rr}× more upside than downside)</span>}
                  {p.basis && <span className="text-txt-3"> — {p.basis}</span>}
                </li>
              ))}
            </ul>
          </Stage>
        )}

        <div className="relative pl-6">
          <span className="absolute -left-[13px] top-0 flex h-6 w-6 items-center justify-center rounded-full border border-edge-strong bg-surface-panel font-num text-[11px] text-txt-2">
            ✓
          </span>
          <h3 className="font-display text-[15px] font-medium text-txt-1">The outcome</h3>
          <div className="mt-2">
            {t.applied.length + t.queued.length === 0
              ? empty('Nothing booked — the desk held.')
              : (
                <ul className="space-y-1">
                  {t.applied.map((c) => bookedRow(c, 'booked'))}
                  {t.queued.map((c) => bookedRow(c, 'awaiting your approval'))}
                </ul>
              )}
            {t.errors.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer font-sans text-[12px] text-txt-3 underline decoration-dotted underline-offset-2">
                  {t.errors.length} idea(s) filtered out by the rulebook
                </summary>
                <ul className="mt-1 list-disc pl-5 font-sans text-[12px] text-txt-3">
                  {t.errors.map((e) => <li key={e.slice(0, 40)}>{e}</li>)}
                </ul>
              </details>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
