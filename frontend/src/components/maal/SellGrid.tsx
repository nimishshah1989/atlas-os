'use client'
// Sell side: EVERY position the real book holds. Weight is the amount trimmed —
// "Full exit" fills in the whole held position.
import { SELL_REASONS, atCapSymbols, type BookPosition } from '@/lib/maal'
import { ChartAttach } from './ChartAttach'
import type { DraftCall } from './draftTypes'

export function SellGrid({
  rows,
  openingBook,
  maxCapPct,
  confirmationId,
  readOnly,
  onChange,
  onRefresh,
}: {
  rows: DraftCall[]
  openingBook: BookPosition[]
  maxCapPct: number
  confirmationId: number | null
  readOnly: boolean
  onChange: (rows: DraftCall[]) => void
  onRefresh: () => void
}) {
  // The cap no longer filters this list — every real holding is sellable. It marks
  // the names that can only come down, so the eye still lands on them first.
  const atCap = new Set(atCapSymbols(openingBook, maxCapPct))

  const update = (i: number, patch: Partial<DraftCall>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const taken = new Set(rows.map((r) => r.key))
  const available = openingBook.filter((p) => !taken.has(p.key))
  const heldOf = (key: string) => openingBook.find((p) => p.key === key)?.weightPct ?? 0

  const addRow = (key: string) => {
    const held = openingBook.find((p) => p.key === key)
    if (!held) return
    onChange([
      ...rows,
      {
        side: 'sell',
        key: held.key,
        symbol: held.symbol,
        name: held.name,
        sector: held.sector,
        weightPct: held.weightPct,
        triggerPrice: null,
        stopPrice: null,
        reasons: [],
        comment: '',
        hasImage: false,
        assetClass: held.key.startsWith('etf:') ? 'etf' : 'stock',
      },
    ])
  }

  const toggleReason = (i: number, reason: string) => {
    const cur = rows[i].reasons
    update(i, { reasons: cur.includes(reason) ? cur.filter((x) => x !== reason) : [...cur, reason] })
  }

  return (
    <section className="rounded-panel border border-edge-hair bg-surface-panel p-4 shadow-tile">
      <h2 className="mb-3 font-num text-[10px] uppercase tracking-[0.14em] text-sig-neg">Sell side</h2>

      {openingBook.length === 0 && (
        <p className="mb-3 font-sans text-[12.5px] italic text-txt-3">
          Nothing held yet — the first report is buys only.
        </p>
      )}
      {rows.length === 0 && openingBook.length > 0 && (
        <p className="mb-3 font-sans text-[12.5px] italic text-txt-3">No sells this week.</p>
      )}

      <div className="space-y-3">
        {rows.map((r, i) => {
          const held = heldOf(r.key)
          const over = r.weightPct > held
          return (
            <div key={i} className="rounded-tile border border-edge-hair bg-surface-base p-3">
              <div className="grid gap-2 md:grid-cols-[1.4fr_0.8fr_0.8fr_2fr_auto_auto] md:items-start">
                <div>
                  <Label>Instrument</Label>
                  <div className="flex items-center gap-1.5 py-1.5">
                    <span className="font-num text-[13px] font-semibold text-txt-1">{r.symbol}</span>
                    {atCap.has(r.symbol) && (
                      <span
                        title="At or within 1% of this book's max position cap — it can only come down"
                        className="rounded-sm bg-sig-neg/10 px-1 py-px font-num text-[9px] uppercase tracking-wider text-sig-neg"
                      >
                        cap
                      </span>
                    )}
                  </div>
                </div>

                <div>
                  <Label>Held</Label>
                  <div className="py-1.5 text-right font-num text-[12.5px] tabular-nums text-txt-2">
                    {held.toFixed(1)}%
                  </div>
                </div>

                <div>
                  <Label>Sell %</Label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    readOnly={readOnly}
                    value={r.weightPct || ''}
                    onChange={(e) => update(i, { weightPct: e.target.value === '' ? 0 : Number(e.target.value) })}
                    className={`w-full rounded-tile border bg-surface-base px-2 py-1.5 text-right font-num text-[12.5px] tabular-nums outline-none ${
                      over ? 'border-sig-neg text-sig-neg' : 'border-edge-rule text-txt-1 focus:border-brand'
                    }`}
                  />
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => update(i, { weightPct: held })}
                      className="mt-0.5 font-sans text-[10px] text-accent hover:underline"
                    >
                      Full exit
                    </button>
                  )}
                </div>

                <div>
                  <Label>Reason</Label>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 pt-1">
                    {SELL_REASONS.map((reason) => (
                      <label key={reason} className="flex items-center gap-1 font-sans text-[11.5px] text-txt-2">
                        <input
                          type="checkbox"
                          disabled={readOnly}
                          checked={r.reasons.includes(reason)}
                          onChange={() => toggleReason(i, reason)}
                        />
                        {reason}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <Label>Chart</Label>
                  {readOnly ? (
                    <span className="font-sans text-[11px] text-txt-3">{r.hasImage ? '✓' : '—'}</span>
                  ) : (
                    <ChartAttach
                      confirmationId={confirmationId}
                      target="call"
                      refKey={r.key}
                      attached={r.hasImage}
                      onDone={onRefresh}
                    />
                  )}
                </div>

                {!readOnly && (
                  <button
                    type="button"
                    onClick={() => onChange(rows.filter((_, j) => j !== i))}
                    aria-label="Remove sell row"
                    className="mt-4 font-sans text-[13px] text-txt-3 hover:text-sig-neg"
                  >
                    ✕
                  </button>
                )}
              </div>

              <div className="mt-2">
                <Label>Comment</Label>
                <textarea
                  value={r.comment}
                  readOnly={readOnly}
                  onChange={(e) => update(i, { comment: e.target.value })}
                  rows={2}
                  placeholder="Optional"
                  className="w-full rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-sans text-[12.5px] text-txt-1 outline-none focus:border-brand"
                />
              </div>
            </div>
          )
        })}
      </div>

      {!readOnly && available.length > 0 && (
        <select
          value=""
          onChange={(e) => e.target.value && addRow(e.target.value)}
          className="mt-3 rounded-tile border border-edge-rule bg-surface-base px-3 py-1.5 font-sans text-[12px] text-txt-2"
        >
          <option value="">+ Add sell from the book…</option>
          {available.map((p) => (
            <option key={p.key} value={p.key}>
              {p.symbol} — {p.weightPct.toFixed(1)}%
            </option>
          ))}
        </select>
      )}
    </section>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-0.5 font-num text-[9px] uppercase tracking-wider text-txt-3">{children}</div>
}
