// frontend/src/components/health/HealthHeader.tsx
import type { HealthHeaderStatus } from '@/lib/queries/health'

const LEVEL_STYLES: Record<HealthHeaderStatus['level'], string> = {
  green: 'bg-sig-pos-soft text-sig-pos border-sig-pos/40',
  yellow: 'bg-sig-warn/10 text-sig-warn border-sig-warn/40',
  red: 'bg-sig-neg-soft text-sig-neg border-sig-neg/40',
}

const LEVEL_LABEL: Record<HealthHeaderStatus['level'], string> = {
  green: 'SYSTEM HEALTHY',
  yellow: 'DEGRADED',
  red: 'CRITICAL',
}

function formatTs(d: Date | null): string {
  if (!d) return '—'
  // DD-MMM-YYYY HH:MM IST
  const date = new Date(d)
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

export function HealthHeader({ status }: { status: HealthHeaderStatus }) {
  return (
    <div
      className={`px-6 py-4 border-b ${LEVEL_STYLES[status.level]}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="font-sans text-[11px] font-semibold tracking-[0.22em]">
            {LEVEL_LABEL[status.level]}
          </div>
          <div className="font-display text-2xl mt-1">{status.message}</div>
        </div>
        <div className="text-right">
          <div className="font-sans text-[11px] tracking-[0.22em] text-txt-3">
            LAST CHECK
          </div>
          <div className="font-num text-sm mt-1 tabular-nums">
            {formatTs(status.last_health_check)}
          </div>
        </div>
      </div>
    </div>
  )
}
