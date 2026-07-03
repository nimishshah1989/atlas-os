'use client'
// AddToBasketButton — the one-cell "+" affordance any table row can drop in.
// Opens the AddToBasketDialog for that single instrument.
import { useState } from 'react'
import { Plus } from 'lucide-react'
import { AddToBasketDialog, type BasketPick } from './AddToBasketDialog'

export function AddToBasketButton({ pick }: { pick: BasketPick }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(true) }}
        aria-label={`Add ${pick.label} to basket`}
        title="Add to basket"
        className="rounded p-0.5 text-txt-3 transition-colors hover:bg-surface-raised hover:text-brand"
      >
        <Plus size={13} />
      </button>
      {open && <AddToBasketDialog picks={[pick]} onClose={() => setOpen(false)} />}
    </>
  )
}
