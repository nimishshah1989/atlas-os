// frontend/src/components/v6/shared/ActionBadge.tsx
//
// Shared action badge for POSITIVE / NEGATIVE / NEUTRAL signal actions.
//
// Used by:
//   - TodayConvictionTabs (landing page conviction rows)
//   - RecentSignalCalls (today page signal call table) — via refactor
//
// Renders a pill with Atlas DS token-based colors (no hardcoded hex).
// label prop controls the display text; defaults map action → readable label.

'use client'

type ActionType = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | string

interface ActionBadgeProps {
  /** Signal action value from DB. */
  action: ActionType
  /**
   * Optional explicit label override.
   * Default mapping: POSITIVE→BUY, NEGATIVE→AVOID, NEUTRAL→WATCH.
   * Pass `action` directly to show raw action string (e.g. for RecentSignalCalls).
   */
  label?: string
}

const ACTION_DEFAULTS: Record<string, string> = {
  POSITIVE: 'BUY',
  NEGATIVE: 'AVOID',
  NEUTRAL: 'WATCH',
}

function actionClasses(action: ActionType): string {
  switch (action) {
    case 'POSITIVE':
      return 'bg-signal-pos/12 text-signal-pos border-signal-pos/30'
    case 'NEGATIVE':
      return 'bg-signal-neg/12 text-signal-neg border-signal-neg/30'
    case 'NEUTRAL':
      return 'bg-signal-warn/12 text-signal-warn border-signal-warn/30'
    default:
      return 'bg-paper-deep text-ink-secondary border-paper-rule'
  }
}

export function ActionBadge({ action, label }: ActionBadgeProps) {
  const displayLabel = label ?? ACTION_DEFAULTS[action] ?? action
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-[2px] font-sans text-[11px] font-semibold border ${actionClasses(action)}`}
    >
      {displayLabel}
    </span>
  )
}
