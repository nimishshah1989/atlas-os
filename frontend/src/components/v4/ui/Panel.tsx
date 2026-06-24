// Layered glass panel — the single surface primitive for v4. Header carries an
// eyebrow + title, an optional self-explaining InfoTip, and an optional action
// (e.g. an "expand" / "see all" link). Body is padded; pass bodyClassName to
// override for flush tables.
import type { ReactNode } from 'react'
import { InfoTip } from './InfoTip'

export function Panel({
  title,
  eyebrow,
  info,
  action,
  children,
  className = '',
  bodyClassName = '',
}: {
  title?: ReactNode
  eyebrow?: string
  info?: { title?: string; body: ReactNode }
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  const hasHeader = title || eyebrow || info || action
  return (
    <section className={`rounded-panel border border-edge-hair bg-surface-panel shadow-panel ${className}`}>
      {hasHeader && (
        <header className="flex items-center gap-2.5 border-b border-edge-hair px-5 py-3.5">
          <div className="min-w-0">
            {eyebrow && <div className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">{eyebrow}</div>}
            {title && <h2 className="font-display text-[15px] font-medium leading-tight text-txt-1">{title}</h2>}
          </div>
          {info && <InfoTip title={info.title}>{info.body}</InfoTip>}
          {action && <div className="ml-auto shrink-0">{action}</div>}
        </header>
      )}
      <div className={bodyClassName || 'px-5 py-4'}>{children}</div>
    </section>
  )
}
