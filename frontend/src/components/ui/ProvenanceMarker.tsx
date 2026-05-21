'use client'
/**
 * ProvenanceMarker — C5 data-integrity component.
 *
 * Renders a subtle "LEGACY" dot-badge with a tooltip when a fund/ETF row's
 * states come from the pre-v2 legacy nightly writer rather than the
 * bottom-up holdings aggregator.
 *
 * Usage: place next to the first state chip in a screener row or detail header.
 *
 * The marker is only rendered when data_source === 'legacy'. Bottom-up rows
 * render nothing (the absence of a marker is the affirmative signal).
 */
import * as Tooltip from '@radix-ui/react-tooltip'

const LEGACY_TOOLTIP =
  'States sourced from the legacy nightly writer (atlas_{fund,etf}_states_daily). ' +
  'The bottom-up holdings aggregator (v2 engine) has not yet computed states for this instrument. ' +
  'Legacy states are computed from NAV momentum and top-level RS, not from constituent holdings.'

type Props = {
  dataSource: 'bottom_up' | 'legacy'
  /** Unique id for the instrument (mstar_id or ticker) — used for data-testid */
  id: string
}

export function ProvenanceMarker({ dataSource, id }: Props) {
  if (dataSource !== 'legacy') return null

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            data-testid={`provenance-legacy-${id}`}
            aria-label="Legacy-sourced data"
            className="inline-flex items-center px-1 py-0 rounded-[2px] font-sans text-[9px] font-semibold tracking-wider bg-amber-100 text-amber-700 border border-amber-200 cursor-help select-none ml-1"
          >
            LEGACY
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            role="tooltip"
            className="z-50 max-w-xs bg-paper border border-paper-rule rounded-[2px] px-3 py-2 text-xs font-sans text-ink-secondary shadow-sm"
            sideOffset={4}
          >
            {LEGACY_TOOLTIP}
            <Tooltip.Arrow className="fill-paper-rule" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
