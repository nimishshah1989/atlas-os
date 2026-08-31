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
  type MaalCode,
  type Problem,
} from '@/lib/maal'
import type { Confirmation } from '@/lib/queries/maal'
import { formatIST } from '@/lib/format-date'
import { BuyGrid } from './BuyGrid'
import { SellGrid } from './SellGrid'
import { EvidenceSections } from './EvidenceSections'
import type { DraftCall, DraftEvidence } from './draftTypes'

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

export function MaalEditor({
  code,
  week,
  openingBook,
  initial,
  maxCapPct,
}: {
  code: MaalCode
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
  const [busy, setBusy] = useState<'save' | 'publish' | 'reopen' | null>(null)
  const [problems, setProblems] = useState<Problem[]>([])
  const [note, setNote] = useState<string | null>(null)

  const buys = calls.filter((c) => c.side === 'buy')
  const sells = calls.filter((c) => c.side === 'sell')
  const named = calls.filter((c) => c.key !== '')
  const move = cashMovement(openingBook, named)
  const resulting = foldBook(openingBook, named)
  const localProblems = validateCalls(openingBook, named)

  // Why publish is unavailable, in the FM's words rather than a greyed-out button.
  // One reason at a time: naming the first blocker is actionable, listing five is noise.
  const publishBlockedBy =
    busy !== null
      ? null
      : named.length === 0
        ? 'Add at least one buy or sell before publishing.'
        : localProblems.length > 0
          ? `Fix ${localProblems.length} issue${localProblems.length > 1 ? 's' : ''} above: ${localProblems[0].message}`
          : null

  const setSide = (side: 'buy' | 'sell') => (rows: DraftCall[]) =>
    setCalls([...(side === 'buy' ? rows : buys), ...(side === 'buy' ? sells : rows)])

  const save = async () => {
    setBusy('save')
    setNote(null)
    setProblems([])
    try {
      const r = await fetch('/api/maal/save', {
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
      const saved = await fetch('/api/maal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, week, calls: named, evidence }),
      })
      if (!saved.ok) {
        const d = await saved.json().catch(() => ({}))
        setProblems([{ code: d.error_code ?? 'error', message: d.message ?? 'save failed' }])
        return
      }
      const r = await fetch('/api/maal/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, week }),
      })
      const d = await r.json()
      if (!r.ok) {
        setProblems(d.problems ?? [{ code: d.error_code ?? 'error', message: d.message ?? 'publish failed' }])
      } else {
        router.push(`/portfolios/maal/${code}/${week}/report`)
      }
    } finally {
      setBusy(null)
    }
  }

  // Publish stays one-way by default (ADR 0003): a circulated report must render the
  // same forever. Reopening is the deliberate exception, so a mistake does not have to
  // wait a week — and it is loud, because the week goes back to DRAFT until republished.
  const reopen = async () => {
    setBusy('reopen')
    setNote(null)
    setProblems([])
    try {
      const r = await fetch('/api/maal/reopen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, week }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) {
        setProblems([{ code: d.error_code ?? 'error', message: d.message ?? 'could not reopen' }])
      } else {
        setNote('Reopened — this week is a draft again. Publish when the changes are ready.')
        router.refresh()
      }
    } finally {
      setBusy(null)
    }
  }

  const shown = problems.length > 0 ? problems : localProblems

  return (
    <div className="space-y-4">
      {published && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-panel border border-sig-pos/30 bg-sig-pos/[0.06] px-4 py-2.5">
          <p className="font-sans text-[12.5px] text-txt-2">
            {initial?.publishedAt
              ? `Published ${formatIST(initial.publishedAt, true)}`
              : 'Published'}{' '}
            — frozen so the circulated report keeps rendering the same.
          </p>
          <button
            type="button"
            onClick={reopen}
            disabled={busy !== null}
            className="rounded-tile border border-edge-rule bg-surface-base px-3 py-1 font-sans text-[12px] text-txt-1 hover:border-edge-strong disabled:opacity-50"
          >
            {busy === 'reopen' ? 'Reopening…' : 'Edit this week'}
          </button>
          <span className="font-sans text-[11px] text-txt-3">
            Reopening returns it to draft — anyone already holding the PDF will have an
            older copy until you publish again.
          </span>
        </div>
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
        blockedKeys={sells.map((s) => s.key).filter(Boolean)}
        confirmationId={confirmationId}
        readOnly={published}
        onChange={setSide('buy')}
        onRefresh={router.refresh}
      />
      <SellGrid
        rows={sells}
        openingBook={openingBook}
        maxCapPct={maxCapPct}
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
            title={publishBlockedBy ?? 'Publish this week and build its report'}
            className="rounded-tile border border-brand/40 bg-brand/10 px-4 py-2 font-sans text-[13px] font-semibold text-brand hover:bg-brand/15 disabled:opacity-40"
          >
            {busy === 'publish' ? 'Publishing…' : 'Publish & build report'}
          </button>
          {/* A greyed-out button that will not say WHY is the actual defect. Name the
              one thing standing in the way, so the FM is never left guessing. */}
          <span
            className={`font-sans text-[11.5px] ${publishBlockedBy ? 'text-sig-neg' : 'text-txt-3'}`}
          >
            {publishBlockedBy ??
              'Publishing freezes this week and builds the report you can download as a PDF.'}
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
