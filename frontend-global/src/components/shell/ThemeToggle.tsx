'use client'
// src/components/shell/ThemeToggle.tsx — day / night. Flips data-theme on <html> (globals.css does
// the rest) and remembers the choice; the pre-paint script in layout.tsx reads it back. Mounted-
// guarded so the server and the first client paint agree.
import { useEffect, useState } from 'react'
import { Icon } from './icons'

export const THEME_STORAGE_KEY = 'atlas-global-theme'

type Theme = 'light' | 'dark'

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('light')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
    setTheme(t)
    setMounted(true)
  }, [])

  function toggle() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // private mode: the choice lasts for this page only
    }
  }

  const label = !mounted ? 'Switch theme' : theme === 'dark' ? 'Switch to day' : 'Switch to night'
  return (
    <button type="button" onClick={toggle} aria-label={label} title={label} className="btn btn-quiet">
      <Icon name={mounted && theme === 'dark' ? 'sun' : 'moon'} />
    </button>
  )
}
