// frontend/src/components/stocks/ComponentValidationRow.tsx
// Single row in the component validation section. Shows one signal component
// (e.g. "Relative strength") alongside its IC-validated badge treatment and stats.
// Pure server component — no interactivity needed.
import type { ComponentValidation } from '@/lib/queries/component_validation'
import { ValidatedBadge } from '@/components/ui/ValidatedBadge'

interface ComponentValidationRowProps {
  /** Human-readable component label, e.g., "Relative strength" */
  componentLabel: string
  /** Badge / tier this stock falls into, e.g., "Leader" */
  badge: string
  /** Validation row for this (component, badge). null/undefined = no IC backing. */
  validation: ComponentValidation | null | undefined
  /**
   * For decorative tiers, pass the continuous value to display instead
   * of the binary badge label.
   */
  decorativeContinuousValue?: string | null
  /**
   * Optional context shown below the badge in font-mono (e.g., "rs_rank 0.92").
   */
  contextLine?: string
}

// ---------------------------------------------------------------------------
// IC stats string — only for validated / validated_inverse / weak
// ---------------------------------------------------------------------------

function buildIcStats(v: ComponentValidation): string | null {
  if (v.status === 'decorative') return null
  const ir = v.ic_ir != null ? `IR ${v.ic_ir >= 0 ? '+' : ''}${v.ic_ir.toFixed(2)}` : null
  const q  = v.q5_q1_spread != null
    ? `Q5-Q1 ${v.q5_q1_spread >= 0 ? '+' : ''}${(v.q5_q1_spread * 100).toFixed(1)}%`
    : null
  const parts = [ir, q].filter(Boolean)
  return parts.length > 0 ? parts.join(' · ') : null
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ComponentValidationRow({
  componentLabel,
  badge,
  validation,
  decorativeContinuousValue,
  contextLine,
}: ComponentValidationRowProps) {
  const icStats = validation ? buildIcStats(validation) : null

  return (
    <div
      className="grid grid-cols-[160px_1fr_auto] items-center gap-4 py-2 border-b border-paper-rule last:border-0"
      data-testid="component-validation-row"
    >
      {/* Left: component label */}
      <div className="font-sans text-[10px] font-semibold text-ink-secondary uppercase tracking-wide">
        {componentLabel}
      </div>

      {/* Middle: badge + optional context line */}
      <div className="flex flex-col gap-0.5">
        <ValidatedBadge
          label={badge}
          validation={validation}
          decorativeContinuousValue={decorativeContinuousValue}
        />
        {contextLine && (
          <div className="font-mono text-[11px] text-ink-tertiary">
            {contextLine}
          </div>
        )}
      </div>

      {/* Right: IC stats */}
      <div className="font-mono text-xs text-ink-tertiary whitespace-nowrap">
        {icStats ?? ''}
      </div>
    </div>
  )
}
