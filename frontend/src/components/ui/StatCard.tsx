// A headline stat tile — the FIRST thing the FM sees (§3.a). Big tabular figure
// is the hero; label is a quiet eyebrow. When `href` is set the whole tile is a
// link (passive → actionable, §1.3) and shows a → affordance on hover.
import Link from 'next/link'
import type { ReactNode } from 'react'

export type Tone = 'pos' | 'neg' | 'neutral' | 'brand' | 'warn'

const TONE: Record<Tone, string> = {
  pos: 'var(--color-sig-pos)',
  neg: 'var(--color-sig-neg)',
  warn: 'var(--color-sig-warn)',
  neutral: 'var(--color-txt-1)',
  brand: 'var(--color-brand)',
}

export function StatCard({
  label,
  value,
  unit,
  sub,
  delta,
  tone = 'neutral',
  href,
  children,
}: {
  label: string
  value: ReactNode
  unit?: string
  sub?: ReactNode
  delta?: { value: string; tone: Tone }
  tone?: Tone
  href?: string
  children?: ReactNode
}) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">{label}</span>
        {href && <span className="font-num text-[12px] text-txt-3 transition-colors group-hover/stat:text-brand">→</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="font-display text-[30px] font-semibold leading-none tracking-tight tabular-nums" style={{ color: TONE[tone] }}>
          {value}
        </span>
        {unit && <span className="font-num text-[13px] text-txt-2">{unit}</span>}
      </div>
      {children && <div className="mt-2.5">{children}</div>}
      {(sub || delta) && (
        <div className="mt-2 flex items-center gap-2">
          {sub && <span className="font-sans text-[11px] text-txt-2">{sub}</span>}
          {delta && (
            <span className="font-num text-[11px] tabular-nums" style={{ color: TONE[delta.tone] }}>
              {delta.value}
            </span>
          )}
        </div>
      )}
    </>
  )
  const base = 'group/stat block rounded-tile border border-edge-hair bg-surface-raised px-4 py-3.5 shadow-tile transition-colors'
  return href ? (
    <Link href={href} className={`${base} hover:border-edge-strong hover:bg-surface-raised`}>
      {body}
    </Link>
  ) : (
    <div className={base}>{body}</div>
  )
}
