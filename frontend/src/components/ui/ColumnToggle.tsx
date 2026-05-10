'use client'
import { useState, useEffect, useRef } from 'react'

export type ColumnDef = {
  key: string
  label: string
  defaultVisible?: boolean
}

export function useColumnVisibility(
  storageKey: string,
  columns: ColumnDef[],
): [Set<string>, (v: Set<string>) => void] {
  const defaultSet = new Set(columns.filter(c => c.defaultVisible !== false).map(c => c.key))
  const [visible, setVisibleState] = useState<Set<string>>(defaultSet)

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) setVisibleState(new Set(JSON.parse(raw) as string[]))
    } catch {
      // ignore
    }
  }, [storageKey])

  function setVisible(v: Set<string>) {
    setVisibleState(v)
    try { localStorage.setItem(storageKey, JSON.stringify([...v])) } catch { /* ignore */ }
  }

  return [visible, setVisible]
}

type Props = {
  columns: ColumnDef[]
  visible: Set<string>
  onChange: (v: Set<string>) => void
}

export function ColumnToggle({ columns, visible, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onOutsideClick)
    return () => document.removeEventListener('mousedown', onOutsideClick)
  }, [open])

  function toggle(key: string) {
    const next = new Set(visible)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onChange(next)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-ink-secondary border border-paper-rule hover:bg-paper-subtle transition-colors"
        aria-expanded={open}
      >
        <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M1 3h10M3 6h6M5 9h2" strokeLinecap="round" />
        </svg>
        Columns
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 bg-paper border border-paper-rule rounded shadow-md p-2 min-w-[160px]">
          {columns.map(col => (
            <label key={col.key} className="flex items-center gap-2 px-1 py-0.5 rounded hover:bg-paper-subtle cursor-pointer text-xs text-ink-secondary">
              <input
                type="checkbox"
                checked={visible.has(col.key)}
                onChange={() => toggle(col.key)}
                className="accent-teal w-3 h-3"
              />
              {col.label}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
