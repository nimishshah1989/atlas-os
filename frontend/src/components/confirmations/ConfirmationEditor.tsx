'use client'
// The Monday document. Buys set target weights, sells trim; the banner narrates
// where the cash moves. Publishing revalidates server-side and freezes the book.
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import {
  cashMovement,
  validateCalls,
  foldBook,
  sellCandidates,
  type BookPosition,
  type PortfolioCode,
  type Problem,
} from '@/lib/confirmations'
import type { Confirmation } from '@/lib/queries/confirmations'
import { formatIST } from '@/lib/format-date'
import { BuyGrid } from './BuyGrid'
import { SellGrid } from './SellGrid'
import { EvidenceSections } from './EvidenceSections'
import type { DraftCall, DraftEvidence } from './draftTypes'

const SIGN_IN_MESSAGE =
  'Not signed in — open /login in a new tab, sign in, then press Save again. Your rows are still here.'

const toDraft = (c: Confirmation['calls'][number]): DraftCall => ({
  side: c.side,
  key: c.key,
  symbol: c.symbol,
  name: c.name,
  sector: c.sector,
  weightPct: c.weightPct,
  triggerPrice: c.triggerPrice,
  stopPrice: c.stopPrice,
  reasons: c.reasons,
  comment: c.comment,
  hasImage: c.hasImage,
  assetClass: c.key.startsWith('etf:') ? 'etf' : 'stock',
})

/** A held position turned into a ready-to-review sell row (weight = full exit). */
const toSellRow = (p: BookPosition): DraftCall => ({
  side: 'sell',
  key: p.key,
  symbol: p.symbol,
  name: p.name,
  sector: p.sector,
  weightPct: p.weightPct,
  triggerPrice: null,
  stopPrice: null,
  reasons: [],
  comment: '',
  hasImage: false,
  assetClass: p.key.startsWith('etf:') ? 'etf' : 'stock',
})

export function ConfirmationEditor({
  code,
  week,
  openingBook,
  initial,
  maxCapPct,
}: {
  code: PortfolioCode
  week: string
  openingBook: BookPosition[]
  initial: Confirmation | null
  maxCapPct: number
}) {
  const router = useRouter()
  const published = initial?.status === 'published'
  // A fresh week opens with the maxed-out positions already on the sell side: they can
  // only come down, so the FM reviews and attaches evidence rather than re-typing names.
  const [calls, setCalls] = useState<DraftCall[]>(
    initial?.calls.length
      ? initial.calls.map(toDraft)
      : sellCandidates(openingBook, maxCapPct).map(toSellRow),
  )
  const [evidence, setEvidence] = useState<DraftEvidence[]>(initial?.evidence ?? [])
  const [confirmationId, setConfirmationId] = useState<number | null>(initial?.confirmationId ?? null)
  const [busy, setBusy] = useState<'save' | 'publish' | null>(null)
  const [problems, setProblems] = useState<Problem[]>([])
  const [note, setNote] = useState<string | null>(null)

  const buys = calls.filter((c) => c.side === 'buy')
  const sells = calls.filter((c) => c.side === 'sell')
  const named = calls.filter((c) => c.key !== '')
  const move = cashMovement(openingBook, named)
  const resulting = foldBook(openingBook, named)
  const localProblems = validateCalls(openingBook, named)

  const setSide = (side: 'buy' | 'sell') => (rows: DraftCall[]) =>
    setCalls([...(side === 'buy' ? rows : buys), ...(side === 'buy' ? sells : rows)])

  const save = async () => {
    setBusy('save')
    setNote(null)
    setProblems([])
    try {
      const r = await fetch('/api/confirmations/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, week, calls: named, evidence }),
      })
      const d = await r.json()
      if (!r.ok) {
        setProblems([{ code: d.error_code ?? 'error', message: d.message ?? 'save failed' }])
      } else {
        setConfirmationId(d.confirmationId)
        setNote('Draft saved.')
        router.refresh()
      }
    } finally {
      setBusy(null)
    }
  }

  const publish = async () => {
    setBusy('publish')
    setNote(null)
    setProblems([])
    try {
      // Always persist first: publish validates what is stored, not what is typed.
      const saved = await fetch('/api/confirmations/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, week, calls: named, evidence }),
      })
      if (!saved.ok) {
        const d = await saved.json().catch(() => ({}))
        setProblems([
          saved.status === 401
            ? { code: 'unauthorized', message: SIGN_IN_MESSAGE }
            : { code: d.error_code ?? 'error', message: d.message ?? 'save failed' },
        ])
        return
      }
      const r = await fetch('/api/confirmations/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, week }),
      })
      const d = await r.json()
      if (!r.ok) {
        setProblems(d.problems ?? [{ code: d.error_code ?? 'error', message: d.message ?? 'publish failed' }])
      } else {
        router.push(`/portfolios/confirmations/${code}/${week}/report`)
      }
    } finally {
      setBusy(null)
    }
  }

  const shown = problems.length > 0 ? problems : localProblems

  return (
    <div className="space-y-4">
      {published && (
        <p className="rounded-panel border border-sig-pos/30 bg-sig-pos/[0.06] px-4 py-2.5 font-sans text-[12.5px] text-txt-2">
          {initial?.publishedAt ? `Published ${formatIST(initial.publishedAt, true)}` : 'Published'} — this
          week is frozen. Start the next Monday to make further changes.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-panel border border-edge-hair bg-surface-raised px-4 py-3">
        <Stat label="Buys" value={String(buys.length)} tone="text-sig-pos" />
        <Stat label="Sells" value={String(sells.length)} tone="text-sig-neg" />
        <Stat label="Sells free" value={`${move.freed.toFixed(1)}%`} />
        <Stat label="Buys deploy" value={`${move.deployed.toFixed(1)}%`} />
        <Stat
          label="Cash"
          value={`${move.before.toFixed(1)}% → ${move.after.toFixed(1)}%`}
          tone={move.after < 0 ? 'text-sig-neg' : 'text-txt-1'}
        />
        <Stat label="Positions after" value={String(resulting.length)} />
        {maxCapPct > 0 && <Stat label="Max cap" value={`${maxCapPct.toFixed(1)}%`} tone="text-sig-warn" />}
      </div>

      {shown.length > 0 && (
        <ul className="space-y-1 rounded-panel border border-sig-neg/30 bg-sig-neg/[0.06] px-4 py-3">
          {shown.map((p, i) => (
            <li key={i} className="font-sans text-[12.5px] text-sig-neg">
              {p.message}
            </li>
          ))}
        </ul>
      )}
      {note && <p className="font-sans text-[12.5px] text-sig-pos">{note}</p>}

      <BuyGrid
        rows={buys}
        confirmationId={confirmationId}
        readOnly={published}
        onChange={setSide('buy')}
        onRefresh={router.refresh}
      />
      <SellGrid
        rows={sells}
        openingBook={openingBook}
        confirmationId={confirmationId}
        readOnly={published}
        onChange={setSide('sell')}
        onRefresh={router.refresh}
      />
      <EvidenceSections
        sections={evidence}
        confirmationId={confirmationId}
        readOnly={published}
        onChange={setEvidence}
        onRefresh={router.refresh}
      />

      {!published && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={busy !== null}
            className="rounded-tile border border-edge-rule bg-surface-base px-4 py-2 font-sans text-[13px] text-txt-1 hover:border-edge-strong disabled:opacity-50"
          >
            {busy === 'save' ? 'Saving…' : 'Save draft'}
          </button>
          <button
            type="button"
            onClick={publish}
            disabled={busy !== null || named.length === 0 || localProblems.length > 0}
            className="rounded-tile border border-brand/40 bg-brand/10 px-4 py-2 font-sans text-[13px] font-semibold text-brand hover:bg-brand/15 disabled:opacity-40"
          >
            {busy === 'publish' ? 'Publishing…' : 'Publish & build report'}
          </button>
          <span className="font-sans text-[11.5px] text-txt-3">
            Publishing rolls the book forward and freezes this week.
          </span>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, tone = 'text-txt-1' }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">{label}</div>
      <div className={`font-num text-[14px] tabular-nums ${tone}`}>{value}</div>
    </div>
  )
}
