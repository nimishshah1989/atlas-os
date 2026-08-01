'use client'
// Attach a chart screenshot to a call row or an evidence section. Uploads to the
// row that is already saved — hence "save the draft first" when there is no id.
import { useRef, useState } from 'react'

export function ChartAttach({
  confirmationId,
  target,
  refKey,
  attached,
  onDone,
}: {
  confirmationId: number | null
  target: 'call' | 'evidence'
  refKey: string
  attached: boolean
  onDone: () => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const send = async (file: File) => {
    if (confirmationId == null) {
      setError('save the draft first')
      return
    }
    setBusy(true)
    setError(null)
    const form = new FormData()
    form.set('file', file)
    form.set('confirmationId', String(confirmationId))
    form.set('target', target)
    form.set('ref', refKey)
    try {
      const r = await fetch('/api/maal/image', { method: 'POST', body: form })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        setError(d.message ?? 'upload failed')
      } else onDone()
    } catch {
      setError('upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-0.5">
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void send(f)
          e.target.value = ''
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className={`rounded-tile border px-2 py-1 font-sans text-[11px] ${
          attached
            ? 'border-sig-pos/40 bg-sig-pos/10 text-sig-pos'
            : 'border-edge-rule bg-surface-base text-txt-3 hover:text-txt-2'
        }`}
      >
        {busy ? 'Uploading…' : attached ? '✓ Chart' : '+ Chart'}
      </button>
      {error && <span className="font-sans text-[10px] text-sig-neg">{error}</span>}
    </div>
  )
}
