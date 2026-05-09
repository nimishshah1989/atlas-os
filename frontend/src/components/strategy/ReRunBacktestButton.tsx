'use client'

import { useState } from 'react'
import { ReRunBacktestModal } from './ReRunBacktestModal'

type Props = {
  strategyId: string
  strategyName: string
  disabled?: boolean
}

export function ReRunBacktestButton({ strategyId, strategyName, disabled = false }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={disabled}
        className="bg-accent text-paper font-sans text-sm px-4 py-2 rounded-[2px] hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Re-run Backtest
      </button>

      {open && (
        <ReRunBacktestModal
          strategyId={strategyId}
          strategyName={strategyName}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
