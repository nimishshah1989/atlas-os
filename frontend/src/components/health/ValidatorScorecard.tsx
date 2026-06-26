// frontend/src/components/health/ValidatorScorecard.tsx
import type { ValidatorRun } from '@/lib/queries/health'

type Stats = {
  validator: 'M3' | 'M4' | 'M5'
  latest: ValidatorRun | null
  passRate: number  // 0..1 over the window
  history: ValidatorRun[]
}

function statsFromRuns(runs: ValidatorRun[]): Stats[] {
  const out: Stats[] = []
  for (const v of ['M3', 'M4', 'M5'] as const) {
    const subset = runs.filter((r) => r.validator === v)
    const sorted = [...subset].sort(
      (a, b) => new Date(b.ran_at).getTime() - new Date(a.ran_at).getTime(),
    )
    const passes = subset.filter((r) => r.status === 'PASS').length
    out.push({
      validator: v,
      latest: sorted[0] ?? null,
      passRate: subset.length === 0 ? 0 : passes / subset.length,
      history: sorted.slice(0, 30).reverse(), // oldest → newest
    })
  }
  return out
}

function Sparkline({ history }: { history: ValidatorRun[] }) {
  if (history.length < 2) {
    return <span className="font-num text-[10px] text-txt-3">—</span>
  }
  const w = 90
  const h = 18
  const step = w / Math.max(history.length - 1, 1)
  const passColor = 'var(--color-sig-pos)'
  const failColor = 'var(--color-sig-neg)'
  return (
    <svg width={w} height={h} aria-hidden="true">
      {history.map((r, i) => {
        const cx = i * step
        const cy = r.status === 'PASS' ? h * 0.3 : h * 0.7
        const fill = r.status === 'PASS' ? passColor : failColor
        return <circle key={r.run_id} cx={cx} cy={cy} r={2.4} fill={fill} />
      })}
    </svg>
  )
}

export function ValidatorScorecard({ runs }: { runs: ValidatorRun[] }) {
  const stats = statsFromRuns(runs)
  return (
    <div className="px-6 py-5 border-b border-edge-hair">
      <h2 className="font-sans text-xs font-medium text-txt-3 uppercase tracking-[0.22em] mb-3">
        Validator scorecard · last 30 days
      </h2>
      <div className="space-y-2">
        {stats.map((s) => {
          const isFail = s.latest?.status === 'FAIL'
          return (
            <div
              key={s.validator}
              className="flex items-center justify-between gap-4 border-b border-edge-hair pb-2 last:border-b-0 last:pb-0"
            >
              <div className="flex items-center gap-3">
                <span className="font-num text-sm w-6">{s.validator}</span>
                {s.latest ? (
                  <span className="font-num text-[12px] tabular-nums">
                    {s.latest.total_checks - s.latest.failures}/{s.latest.total_checks}{' '}
                    <span
                      className={
                        isFail ? 'text-sig-neg' : 'text-sig-pos'
                      }
                    >
                      {s.latest.status}
                    </span>
                  </span>
                ) : (
                  <span className="font-num text-[12px] text-txt-3">no runs</span>
                )}
              </div>
              <div className="flex items-center gap-4">
                <Sparkline history={s.history} />
                <span className="font-num text-[12px] tabular-nums w-12 text-right">
                  {(s.passRate * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
