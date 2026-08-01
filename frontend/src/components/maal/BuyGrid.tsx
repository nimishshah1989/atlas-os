'use client'
// Buy side: pick an instrument from the Atlas universe, state the weight the
// position should END UP at, and say why. Sector fills itself from the pick.
import { useState } from 'react'

import { InstrumentAutocomplete, type Hit } from '@/components/portfolios/InstrumentAutocomplete'
import { ChartAttach } from './ChartAttach'
import type { DraftCall } from './draftTypes'

export function BuyGrid({
  rows,
  blockedKeys,
  confirmationId,
  readOnly,
  onChange,
  onRefresh,
}: {
  rows: DraftCall[]
  /** Keys already on the SELL side — the same name cannot be on both. */
  blockedKeys: string[]
  confirmationId: number | null
  readOnly: boolean
  onChange: (rows: DraftCall[]) => void
  onRefresh: () => void
}) {
  const update = (i: number, patch: Partial<DraftCall>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const addRow = () =>
    onChange([
      ...rows,
      {
        side: 'buy',
        key: '',
        symbol: '',
        name: '',
        sector: null,
        weightPct: 0,
        triggerPrice: null,
        stopPrice: null,
        reasons: [],
        comment: '',
        hasImage: false,
        assetClass: 'stock',
      },
    ])

  const [pickError, setPickError] = useState<string | null>(null)

  // The same name cannot be on both sides. The database enforces it and publish
  // validates it, but both of those tell the FM only AFTER the work is done —
  // refusing the pick is the moment it is cheap to correct.
  const pick = (i: number, h: Hit) => {
    if (blockedKeys.includes(h.key)) {
      setPickError(`${h.label} is already on the sell side — remove it there first.`)
      return
    }
    setPickError(null)
    update(i, { key: h.key, symbol: h.label, name: h.sublabel, sector: h.sector })
  }

  return (
    <section className="rounded-panel border border-edge-hair bg-surface-panel p-4 shadow-tile">
      <h2 className="mb-3 font-num text-[10px] uppercase tracking-[0.14em] text-sig-pos">Buy side</h2>

      {rows.length === 0 && (
        <p className="mb-3 font-sans text-[12.5px] italic text-txt-3">No buys this week.</p>
      )}
      {pickError && (
        <p className="mb-3 font-sans text-[12px] text-sig-neg">{pickError}</p>
      )}

      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="rounded-tile border border-edge-hair bg-surface-base p-3">
            <div className="grid gap-2 md:grid-cols-[1.6fr_0.7fr_1fr_0.8fr_0.8fr_auto_auto] md:items-start">
              <div>
                <Label>Instrument</Label>
                {r.key && !readOnly ? (
                  <div className="flex items-center gap-1.5 py-1.5">
                    <span className="font-num text-[13px] font-semibold text-txt-1">{r.symbol}</span>
                    <button
                      type="button"
                      onClick={() => update(i, { key: '', symbol: '', name: '', sector: null })}
                      className="font-sans text-[11px] text-txt-3 hover:text-sig-neg"
                    >
                      change
                    </button>
                  </div>
                ) : r.key ? (
                  <div className="py-1.5 font-num text-[13px] font-semibold text-txt-1">{r.symbol}</div>
                ) : (
                  <>
                    <select
                      value={r.assetClass}
                      onChange={(e) => update(i, { assetClass: e.target.value as 'stock' | 'etf' })}
                      className="mb-1 w-full rounded-tile border border-edge-rule bg-surface-base px-2 py-1 font-sans text-[11px] text-txt-2"
                    >
                      <option value="stock">Stock</option>
                      <option value="etf">ETF</option>
                    </select>
                    <InstrumentAutocomplete assetClass={r.assetClass} onPick={(h) => pick(i, h)} />
                  </>
                )}
              </div>

              <Num
                label="Weight %"
                value={r.weightPct || null}
                readOnly={readOnly}
                onChange={(v) => update(i, { weightPct: v ?? 0 })}
              />

              <div>
                <Label>Sector</Label>
                <div className="truncate py-1.5 font-sans text-[12px] text-txt-2">{r.sector ?? '—'}</div>
              </div>

              <Num label="Trigger ₹" value={r.triggerPrice} readOnly={readOnly} onChange={(v) => update(i, { triggerPrice: v })} />
              <Num label="Stop ₹" value={r.stopPrice} readOnly={readOnly} onChange={(v) => update(i, { stopPrice: v })} />

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
                  aria-label="Remove buy row"
                  className="mt-4 font-sans text-[13px] text-txt-3 hover:text-sig-neg"
                >
                  ✕
                </button>
              )}
            </div>

            <div className="mt-2">
              <Label>Why this stock</Label>
              <textarea
                value={r.comment}
                readOnly={readOnly}
                onChange={(e) => update(i, { comment: e.target.value })}
                rows={2}
                placeholder="The weight of evidence behind the call"
                className="w-full rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-sans text-[12.5px] text-txt-1 outline-none focus:border-brand"
              />
            </div>
          </div>
        ))}
      </div>

      {!readOnly && (
        <button
          type="button"
          onClick={addRow}
          className="mt-3 rounded-tile border border-edge-rule bg-surface-base px-3 py-1.5 font-sans text-[12px] text-txt-2 hover:border-edge-strong"
        >
          + Add buy
        </button>
      )}
    </section>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-0.5 font-num text-[9px] uppercase tracking-wider text-txt-3">{children}</div>
}

function Num({
  label,
  value,
  readOnly,
  onChange,
}: {
  label: string
  value: number | null
  readOnly: boolean
  onChange: (v: number | null) => void
}) {
  return (
    <div>
      <Label>{label}</Label>
      <input
        type="number"
        step="0.1"
        min="0"
        readOnly={readOnly}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="w-full rounded-tile border border-edge-rule bg-surface-base px-2 py-1.5 text-right font-num text-[12.5px] tabular-nums text-txt-1 outline-none focus:border-brand"
      />
    </div>
  )
}
