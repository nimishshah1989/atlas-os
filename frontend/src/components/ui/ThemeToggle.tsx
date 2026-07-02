'use client'
// Day / night switch. Flips data-theme on <html> (the CSS in globals.css does
// the rest) and persists the choice; the pre-paint script in layout.tsx reads
// it back. Mounted-guarded so SSR and client agree on first paint.
import { useEffect, useState } from 'react'
import { Sun, Moon } from 'lucide-react'

export function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = (document.documentElement.getAttribute('data-theme') as 'light' | 'dark') || 'light'
    setTheme(t)
    setMounted(true)
  }, [])

  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    try { localStorage.setItem('atlas-theme', next) } catch { /* private mode */ }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={mounted ? `Switch to ${theme === 'dark' ? 'day' : 'night'} view` : 'Toggle day / night view'}
      className="grid h-7 w-7 place-items-center rounded-tile border border-edge-rule text-txt-2 transition-colors hover:border-edge-strong hover:text-txt-1"
    >
      {mounted && theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  )
}
