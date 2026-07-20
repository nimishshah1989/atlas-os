// Shared plain-language desk views — one desk's nightly cycle ("what it did and
// why", no jargon) and its report card. Used by both the /desk overview and each
// desk's portfolio detail page, so the two never drift. Server components; every
// value is journaled engine output.
import Link from 'next/link'

import type { DeskCard, DeskCycle, TrackRow } from '@/lib/queries/deskBoard'

const rupeesLakh = (v: number | null) => (v === null ? '—' : `₹${(v / 100000).toFixed(2)} lakh`)
const money = (v: number | null) => (v === null ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`)

export const CHARTER_PLAIN: Record<string, string> = {
  sector_leaders: 'Backs the strongest stocks inside the strongest sectors.',
  conviction: 'Owns the market’s highest-conviction names, wherever they are.',
  quality_momentum: 'Only strong stocks that are also beating the market and trending up.',
  rotation: 'Tries to catch sectors early, as they turn from weak to strong.',
}

const confidenceWord = (c: number | null) =>
  c === null ? null : c >= 4 ? 'high confidence' : c === 3 ? 'medium confidence' : 'low confidence'

function headline(d: DeskCycle): string {
  const sells = [...d.applied, ...d.queued].filter((c) => c.side === 'sell').length
  const buys = [...d.applied, ...d.queued].filter((c) => c.side === 'buy').length
  const queued = d.queued.length > 0
  if (sells + buys === 0) return 'No changes this cycle — nothing looked worth acting on, so it held everything.'
  const parts: string[] = []
  if (buys) parts.push(`${buys} ${buys === 1 ? 'buy' : 'buys'}`)
  if (sells) parts.push(`${sells} ${sells === 1 ? 'sell' : 'sells'}`)
  return `It ${queued ? 'proposed' : 'made'} ${parts.join(' and ')}${queued ? ' — waiting for your approval' : ''}.`
}

function ActionRow({ c }: { c: DeskCard }) {
  const bought = c.side === 'buy'
  const conf = confidenceWord(c.conviction)
  return (
    <li className="border-t border-edge-hair pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className={`font-num text-[12px] font-semibold ${bought ? 'text-sig-pos' : 'text-sig-neg'}`}>
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
          if it drops to <b className="font-num">{money(c.stop)}</b> the desk sells to cap the loss; it aims to take
          profit near <b className="font-num">{money(c.target)}</b>.
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

// The "what it did and why" content for ONE desk. No outer Panel — callers wrap.
export function DeskCycleBody({ cycle: d, detailHref }: { cycle: DeskCycle; detailHref?: string }) {
  const gain = d.nav !== null && d.startCapital !== null ? d.nav - d.startCapital : null
  const gainPct = gain !== null && d.startCapital ? (gain / d.startCapital) * 100 : null
  const actions = [...d.applied, ...d.queued]
  const shortName = d.name.replace('Atlas Desk — ', '')

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-[17px] font-medium text-txt-1">{shortName}</h3>
          <p className="mt-0.5 font-sans text-[12px] text-txt-3">{CHARTER_PLAIN[d.charter] ?? ''}</p>
        </div>
        <div className="text-right">
          <p className="font-num text-[17px] font-medium text-txt-1">{rupeesLakh(d.nav)}</p>
          <p className="font-num text-[11px] text-txt-3">
            {gain !== null && gainPct !== null ? (
              <>
                <span className={gain >= 0 ? 'text-sig-pos' : 'text-sig-neg'}>
                  {gain >= 0 ? '▲' : '▼'} {money(Math.abs(gain))} ({gainPct >= 0 ? '+' : ''}
                  {gainPct.toFixed(1)}%)
                </span>{' '}
                since it started with {rupeesLakh(d.startCapital)}
              </>
            ) : (
              'paper money'
            )}
          </p>
        </div>
      </div>

      <p className="mt-3 font-sans text-[13.5px] text-txt-1">
        <span className="text-txt-3">{d.cycleDate}: </span>
        {headline(d)}
      </p>

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
                  <b>{p.symbol}</b> — considered{' '}
                  {p.action === 'add' ? 'buying' : p.action === 'exit' ? 'selling' : 'watching'};{' '}
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

      {detailHref && (
        <Link
          href={detailHref}
          className="mt-3 inline-block font-sans text-[12px] text-accent no-underline hover:underline"
        >
          See this fund’s full history →
        </Link>
      )}
    </div>
  )
}

// The plain report card — how good this desk's (or the whole desk's) past calls were.
export function DeskReportCard({ track }: { track: TrackRow[] }) {
  if (track.length === 0) return null
  return (
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
              <span className="text-txt-3">{c.dim === 'charter' ? 'strategy' : 'sector'}: </span>
              {c.dimValue.replace('_', ' ')}
            </td>
            <td className="py-1.5 text-right">{c.n}</td>
            <td className="py-1.5 text-right">{(c.hitRate * 100).toFixed(0)}%</td>
            <td className={`py-1.5 text-right ${c.avgAlpha >= 0 ? 'text-sig-pos' : 'text-sig-neg'}`}>
              {c.avgAlpha >= 0 ? '+' : ''}
              {c.avgAlpha.toFixed(1)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
