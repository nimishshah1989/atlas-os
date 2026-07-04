'use client'
// DeskLog — the Atlas Desk's nightly diary: what the Scout flagged, what Risk &
// Tax ruled, what the PM did (with thesis + invalidation per order), and what was
// actually booked. Every line is stored desk_journal output — the glass-box audit
// of the agent's daily judgment.
import { useState } from 'react'
import type { DeskCycle } from '@/lib/queries/portfolios'

type Proposal = { symbol: string; action: string; evidence?: string[]; urgency?: string }
type Verdict = { symbol: string; verdict: string; reason: string }
type Order = { symbol: string; side: string; thesis?: string; invalidation?: string }

function Cycle({ c }: { c: DeskCycle }) {
  const [open, setOpen] = useState(false)
  const proposals = (c.scout?.proposals as Proposal[] | undefined) ?? []
  const verdicts = (c.risk?.verdicts as Verdict[] | undefined) ?? []
  const orders = (c.pm?.orders as Order[] | undefined) ?? []
  const summary =
    c.applied.length > 0
      ? `${c.applied.length} order(s) booked`
      : proposals.length > 0
        ? `held — ${proposals.length} proposal(s), none cleared Risk`
        : 'held — nothing material changed'
  return (
    <div className="border-b border-edge-hair py-2.5">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 text-left">
        <span className="shrink-0 font-num text-[11px] tabular-nums text-txt-3">{c.d}</span>
        <span
          className={`shrink-0 rounded-tile border px-2 py-0.5 font-sans text-[10px] font-semibold uppercase tracking-wider ${
            c.applied.length > 0
              ? 'border-sig-pos/30 bg-sig-pos/10 text-sig-pos'
              : 'border-edge-rule bg-surface-raised text-txt-3'
          }`}
        >
          {c.applied.length > 0 ? 'Traded' : 'Held'}
        </span>
        <span className="flex-1 truncate font-sans text-[12px] text-txt-2">{summary}</span>
        <span className="shrink-0 font-num text-[10px] text-txt-3">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 pl-2 font-sans text-[11.5px] leading-[1.5] text-txt-2">
          {proposals.length > 0 && (
            <div>
              <p className="font-num text-[9px] uppercase tracking-wider text-txt-3">Scout</p>
              {proposals.map((p, i) => (
                <p key={i}>
                  <strong className="font-num text-txt-1">{p.symbol}</strong> · {p.action}
                  {p.urgency === 'high' ? ' · urgent' : ''} — {(p.evidence ?? []).join('; ')}
                </p>
              ))}
            </div>
          )}
          {verdicts.length > 0 && (
            <div>
              <p className="font-num text-[9px] uppercase tracking-wider text-txt-3">Risk &amp; Tax</p>
              {verdicts.map((v, i) => (
                <p key={i}>
                  <strong className="font-num text-txt-1">{v.symbol}</strong> ·{' '}
                  <span className={v.verdict === 'approve' ? 'text-sig-pos' : v.verdict === 'veto' ? 'text-sig-neg' : 'text-sig-warn'}>
                    {v.verdict}
                  </span>{' '}
                  — {v.reason}
                </p>
              ))}
            </div>
          )}
          {orders.length > 0 && (
            <div>
              <p className="font-num text-[9px] uppercase tracking-wider text-txt-3">Portfolio Manager</p>
              {orders.map((o, i) => (
                <p key={i}>
                  <strong className={`font-num ${o.side === 'buy' ? 'text-sig-pos' : 'text-sig-neg'}`}>
                    {o.side.toUpperCase()} {o.symbol}
                  </strong>{' '}
                  — {o.thesis} <em className="text-txt-3">Exit if: {o.invalidation}</em>
                </p>
              ))}
            </div>
          )}
          {c.errors.length > 0 && (
            <p className="text-txt-3">Notes: {c.errors.join(' · ')}</p>
          )}
        </div>
      )}
    </div>
  )
}

export function DeskLog({ cycles }: { cycles: DeskCycle[] }) {
  if (cycles.length === 0)
    return <p className="font-sans text-[13px] italic text-txt-3">First nightly cycle pending.</p>
  return <div>{cycles.map((c, i) => <Cycle key={i} c={c} />)}</div>
}
