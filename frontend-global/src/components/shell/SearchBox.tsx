'use client'
// src/components/shell/SearchBox.tsx — the top bar's search (⌘K / Ctrl+K focuses it). On an
// explorer page it filters the loaded list as you type by writing `q` into the URL, which the
// explorer reads (history.replaceState, no request); anywhere else, Enter opens the ETF explorer
// with the query. Escape clears it.
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Icon } from './icons'

const EXPLORERS = ['/etfs', '/stocks']

export function SearchBox() {
  const pathname = usePathname()
  const params = useSearchParams()
  const router = useRouter()
  const input = useRef<HTMLInputElement>(null)
  const onExplorer = EXPLORERS.includes(pathname)
  const urlQ = onExplorer ? (params.get('q') ?? '') : ''
  const [text, setText] = useState(urlQ)

  // A navigation (or an explorer's own write) is the source of truth for the box.
  useEffect(() => setText(urlQ), [urlQ, pathname])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        input.current?.focus()
        input.current?.select()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  function writeQ(q: string) {
    const p = new URLSearchParams(params.toString())
    if (q) p.set('q', q)
    else p.delete('q')
    const qs = p.toString()
    window.history.replaceState(null, '', qs ? `${pathname}?${qs}` : pathname)
  }

  function change(q: string) {
    setText(q)
    if (onExplorer) writeQ(q)
  }

  function keyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !onExplorer && text.trim()) router.push(`/etfs?q=${encodeURIComponent(text.trim())}`)
    if (e.key === 'Escape') {
      change('')
      input.current?.blur()
    }
  }

  return (
    <label className="search">
      <Icon name="search" />
      <input
        ref={input}
        type="search"
        value={text}
        onChange={(e) => change(e.target.value)}
        onKeyDown={keyDown}
        placeholder="Search symbol or name"
        aria-label="Search symbol or name"
        autoComplete="off"
        spellCheck={false}
      />
      <kbd aria-hidden="true">⌘K</kbd>
    </label>
  )
}
