'use client'
import * as Tooltip from '@radix-ui/react-tooltip'
import { Info } from 'lucide-react'

type Props = {
  content: string
  className?: string
}

export function InfoTooltip({ content, className = '' }: Props) {
  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            aria-label="info"
            className={`inline-flex items-center justify-center w-[18px] h-[18px] rounded-full border-2 border-ink-secondary text-ink-secondary hover:border-ink-primary hover:text-ink-primary transition-colors ml-1 shrink-0 ${className}`}
          >
            <Info size={12} strokeWidth={2.5} />
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            className="z-50 max-w-xs bg-paper border border-paper-rule rounded-[2px] px-3 py-2 text-xs font-sans text-ink-secondary shadow-sm"
            sideOffset={4}
          >
            {content}
            <Tooltip.Arrow className="fill-paper-rule" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
