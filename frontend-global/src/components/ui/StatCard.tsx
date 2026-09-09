// src/components/ui/StatCard.tsx — a headline stat tile, ported from Atlas India's
// frontend/src/components/ui/StatCard.tsx: big tabular figure as the hero, label as a quiet
// eyebrow, and the whole tile a link when there is somewhere to go (passive → actionable).
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
  tone = 'neutral',
  /** Overrides `tone` — for a figure drawn on the decile ramp, where the colour IS the decile. */
  colour,
  href,
  children,
}: {
  label: string
  value: ReactNode
  unit?: string
  sub?: ReactNode
  tone?: Tone
  colour?: string | null
  href?: string
  children?: ReactNode
}) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-meta uppercase tracking-[0.14em] text-ink-3">{label}</span>
        {href && <span className="text-meta text-ink-3 transition-colors group-hover/stat:text-accent">→</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span
          className="num text-[28px] font-semibold leading-none tracking-tight"
          style={{ color: colour ?? TONE[tone] }}
        >
          {value}
        </span>
        {unit && <span className="num text-table text-ink-2">{unit}</span>}
      </div>
      {children && <div className="mt-2.5">{children}</div>}
      {sub && <div className="mt-2 text-meta text-ink-2">{sub}</div>}
    </>
  )
  const base =
    'group/stat block rounded-tile border border-edge-hair bg-surface-raised px-4 py-3.5 shadow-tile transition-colors'
  return href ? (
    <Link href={href} className={`${base} no-underline hover:border-edge-strong`}>
      {body}
    </Link>
  ) : (
    <div className={base}>{body}</div>
  )
}
