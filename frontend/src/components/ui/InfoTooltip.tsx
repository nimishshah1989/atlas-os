'use client'
import * as Tooltip from '@radix-ui/react-tooltip'
import { Info } from 'lucide-react'
import { useId } from 'react'

type Props = {
  content: string
  /** Optional plain-English translation rendered as a second line prefixed with ↳ */
  translation?: string
  className?: string
}

export function InfoTooltip({ content, translation, className = '' }: Props) {
  const tooltipId = useId()

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            aria-label="info"
            aria-describedby={tooltipId}
            className={`inline-flex items-center justify-center w-[18px] h-[18px] rounded-full border-2 border-ink-secondary text-ink-secondary hover:border-ink-primary hover:text-ink-primary transition-colors ml-1 shrink-0 ${className}`}
          >
            <Info size={12} strokeWidth={2.5} />
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            id={tooltipId}
            className="z-50 max-w-[220px] bg-paper border border-paper-rule rounded-[2px] px-2.5 py-1.5 text-[11px] font-sans text-ink-secondary shadow-sm"
            sideOffset={4}
          >
            <span>{content}</span>
            {translation != null && (
              <span className="block mt-0.5 text-[0.7rem] text-ink-tertiary">
                &#x21B3;&nbsp;{translation}
              </span>
            )}
            <Tooltip.Arrow className="fill-paper-rule" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
