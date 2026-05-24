// frontend/src/components/ui/ValidatedBadge.tsx
// Reusable server component. Visual treatment follows atlas_component_validation.status.
// No 'use client' — pure server component. No runtime state needed.
// Tooltip via native HTML title attribute to keep this foundational component free of
// @radix-ui dependencies. Consuming components can wrap with InfoTooltip if richer
// tooltip behaviour is required.
import type { ComponentValidation } from '@/lib/queries/component_validation'

interface ValidatedBadgeProps {
  /** Display label, e.g., "Leader", "Stage 2C", "Elevated Vol" */
  label: string
  /**
   * Validation row from atlas_component_validation.
   * If null/undefined, renders as plain text (no IC backing in our system).
   */
  validation: ComponentValidation | null | undefined
  /**
   * Optional override for the displayed value when validation is decorative.
   * When provided, renders this continuous value instead of the binary label.
   */
  decorativeContinuousValue?: string | null
  /** Optional size variant */
  size?: 'sm' | 'md'
}

/**
 * Renders a badge whose visual treatment matches the per-tier IC validation status:
 *   - validated:         signal-pos text, full label, IC tooltip
 *   - validated_inverse: signal-warn text, counter-intuitive tooltip
 *   - weak:              ink-tertiary with asterisk, weakly-predictive tooltip
 *   - decorative:        if decorativeContinuousValue provided, render that;
 *                        else plain text label with no implied action
 *
 * Design system: sentence case for body copy; ALL CAPS only for tier labels.
 * Tokens: signal-pos, signal-neg, signal-warn, ink-primary, ink-secondary, ink-tertiary.
 */
export function ValidatedBadge({
  label,
  validation,
  decorativeContinuousValue = null,
  size = 'md',
}: ValidatedBadgeProps) {
  const textSize = size === 'sm' ? 'text-[11px]' : 'text-xs'

  // No validation row — badge has no IC backing; render as plain text
  if (!validation) {
    return (
      <span className={`font-sans ${textSize} text-ink-tertiary`}>{label}</span>
    )
  }

  const { status, ic_ir, q5_q1_spread, horizon_days, implied_action } = validation
  const ir = ic_ir ?? 0
  const q = q5_q1_spread ?? 0
  const tooltipBase = `IR ${ir.toFixed(2)} · Q5-Q1 ${(q * 100).toFixed(2)}% at ${horizon_days}d`

  if (status === 'validated') {
    const isPositive = ir >= 0
    const colorClass = isPositive ? 'text-signal-pos' : 'text-signal-neg'
    const verb = implied_action.replace(/_/g, ' ')
    return (
      <span
        className={`inline-flex items-center gap-1 font-sans ${textSize} font-medium ${colorClass}`}
        title={`${verb} · ${tooltipBase}`}
      >
        <span aria-hidden="true">●</span>
        {label}
      </span>
    )
  }

  if (status === 'validated_inverse') {
    return (
      <span
        className={`inline-flex items-center gap-1 font-sans ${textSize} font-medium text-signal-warn`}
        title={`Historically anti-predictive at ${horizon_days}d · ${tooltipBase}`}
      >
        <span aria-hidden="true">◐</span>
        {label}
      </span>
    )
  }

  if (status === 'weak') {
    return (
      <span
        className={`font-sans ${textSize} text-ink-tertiary`}
        title={`Weakly predictive · ${tooltipBase} · informational only`}
      >
        {label}
        <sup>*</sup>
      </span>
    )
  }

  // status === 'decorative'
  if (decorativeContinuousValue !== null && decorativeContinuousValue !== undefined) {
    return (
      <span
        className={`font-mono ${textSize} text-ink-secondary`}
        title="Tier-binarized signal is decorative; continuous value shown instead."
      >
        {decorativeContinuousValue}
      </span>
    )
  }
  return (
    <span className={`font-sans ${textSize} text-ink-tertiary`}>{label}</span>
  )
}
