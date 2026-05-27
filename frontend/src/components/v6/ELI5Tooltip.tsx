// frontend/src/components/v6/ELI5Tooltip.tsx
//
// Wraps any technical term with a Radix tooltip that surfaces the L1 ELI5
// copy from `lib/eli5-registry.ts` plus a "Math →" link to /methodology.
// Uses the dotted-underline style for the wrapped text — that's the
// affordance the user looks for.

'use client'

import * as Tooltip from '@radix-ui/react-tooltip'
import Link from 'next/link'
import { eli5For } from '@/lib/eli5-registry'

type Props = {
  /** Registry key — e.g. "quality_momentum" or "ic_mean". */
  term: string
  /** The visible text being wrapped. Defaults to the term itself. */
  children?: React.ReactNode
  /** Optional class on the wrapper. */
  className?: string
}

export function ELI5Tooltip({ term, children, className = '' }: Props) {
  const entry = eli5For(term)
  if (!entry) {
    // No registry hit — render the children un-decorated so we don't pretend.
    return <span className={className}>{children ?? term}</span>
  }
  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={`underline decoration-dotted decoration-ink-tertiary underline-offset-2 cursor-help ${className}`}
            tabIndex={0}
          >
            {children ?? term}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={4}
            className="z-50 max-w-sm bg-paper border border-paper-rule rounded-[2px] px-3 py-2.5 text-xs font-sans text-ink-secondary shadow-sm leading-relaxed"
          >
            <span className="block">{entry.text}</span>
            {entry.mathAnchor && (
              <Link
                href={`/methodology#${entry.mathAnchor}`}
                className="inline-block mt-1.5 font-sans text-[11px] text-teal hover:underline"
              >
                Math →
              </Link>
            )}
            <Tooltip.Arrow className="fill-paper-rule" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
