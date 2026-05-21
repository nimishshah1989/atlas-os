// frontend/src/components/health/KnownGapsPanel.tsx
// Static honest note about known data gaps — no live query, no fake green status.
// Last reviewed 2026-05-20.

type GapSeverity = 'stale' | 'warn' | 'ok'

interface GapEntry {
  id: string
  severity: GapSeverity
  title: string
  detail: string
}

const KNOWN_GAPS: GapEntry[] = [
  {
    id: 'holdings-stale',
    severity: 'stale',
    title: 'Monthly holdings ingestion — stale',
    detail:
      'de_mf_holdings and de_etf_holdings are stuck at approximately 2026-05-04. The upstream JIP shareholding_pattern job failed; the holdings data has not refreshed since. Fund and ETF bottom-up conviction rankings that depend on current holdings will use stale constituent weights until the job recovers.',
  },
  {
    id: 'adjustment-factors-stale',
    severity: 'stale',
    title: 'Adjustment factors — ~26 days stale',
    detail:
      'de_adjustment_factors_daily has not refreshed in approximately 26 days. Corporate action adjustments (splits, bonuses) applied after the stale date may not be reflected in price-based signals for affected stocks.',
  },
  {
    id: 'state-engine-coverage',
    severity: 'ok',
    title: 'v2 state engine — classified daily, current to T-1',
    detail:
      'The Weinstein state engine classifies the full ~1,000-stock universe nightly. Stock states (RS, Momentum, Risk, Volume, Stage), sector aggregations, conviction scores, and regime breadth are all current to the previous trading day (T-1). The nightly pipeline runs on a cron schedule; data is available from early morning IST.',
  },
  {
    id: 'validator-role',
    severity: 'ok',
    title: 'Data Validator — nightly automated audit',
    detail:
      'The data validator checks every frontend data point against its backend source and classifies findings into six issue classes: gaps (missing rows/NULLs), inconsistencies (frontend vs backend mismatch), calculation errors (derived values that do not match formula output), accuracy errors (values out of domain), insensible values (logically suspicious combinations), and incomplete data (missing columns or date ranges). It runs nightly, pre-milestone, and on-demand. Results appear in the Validator Scorecard below.',
  },
]

const SEV_STYLE: Record<GapSeverity, string> = {
  stale: 'border-l-signal-neg bg-signal-neg-soft',
  warn:  'border-l-signal-warn bg-signal-warn-soft',
  ok:    'border-l-signal-pos bg-signal-pos-soft',
}

const SEV_LABEL: Record<GapSeverity, string> = {
  stale: 'STALE',
  warn:  'WARN',
  ok:    'OK',
}

const SEV_LABEL_STYLE: Record<GapSeverity, string> = {
  stale: 'text-signal-neg-strong',
  warn:  'text-signal-warn-strong',
  ok:    'text-signal-pos-strong',
}

export function KnownGapsPanel() {
  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-sans text-xs font-medium text-ink-3 uppercase tracking-[0.22em]">
          Known data gaps
        </h2>
        <span className="font-sans text-[10px] text-ink-4">
          Last reviewed 2026-05-20
        </span>
      </div>
      <p className="font-sans text-[11px] text-ink-secondary mb-4 leading-relaxed">
        The items below are known, standing data gaps that the live pipeline metrics above may not
        fully capture. They are listed honestly — no item is presented as green when it is not.
        The live freshness table above is the authoritative source for day-to-day lag.
      </p>
      <ul className="space-y-3">
        {KNOWN_GAPS.map((gap) => (
          <li
            key={gap.id}
            className={`border-l-4 px-4 py-3 ${SEV_STYLE[gap.severity]}`}
          >
            <div className="flex items-baseline gap-2 mb-1">
              <span
                className={`font-sans text-[10px] font-semibold tracking-[0.18em] uppercase ${SEV_LABEL_STYLE[gap.severity]}`}
              >
                {SEV_LABEL[gap.severity]}
              </span>
              <span className="font-sans text-[12px] font-medium text-ink-primary">
                {gap.title}
              </span>
            </div>
            <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
              {gap.detail}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}
