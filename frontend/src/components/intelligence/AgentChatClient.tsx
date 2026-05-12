'use client'
// SP07 — Client-side chat island. Maintains an in-memory conversation;
// every submit fires POST /api/agents/invoke and appends the reply.
// No streaming yet (SP07 v2 will add SSE). Reply latency typically 2-5s.
import { useState, useRef, useEffect } from 'react'

type ToolCall = {
  tool: string
  args: Record<string, unknown>
  result_keys: string[]
}

type Message =
  | { role: 'user'; text: string; ts: string }
  | {
      role: 'agent'
      agent: string
      text: string
      tool_calls: ToolCall[]
      data_as_of: string | null
      input_tokens: number | null
      output_tokens: number | null
      iterations: number
      ts: string
    }
  | { role: 'error'; text: string; ts: string }

const AGENTS: string[] = [
  'auto',
  'regime_watcher',
  'sector_rotation',
  'stock_screener',
  'drift_detector',
]

export function AgentChatClient() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [agent, setAgent] = useState<string>('auto')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function submit() {
    const q = input.trim()
    if (!q || busy) return
    const ts = new Date().toISOString()
    setMessages((m) => [...m, { role: 'user', text: q, ts }])
    setInput('')
    setBusy(true)
    try {
      const resp = await fetch('/api/agents/invoke', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent, question: q, persist: true }),
      })
      const body = await resp.json()
      if (!resp.ok) {
        const detail =
          typeof body?.detail === 'string'
            ? body.detail
            : JSON.stringify(body?.detail ?? body)
        setMessages((m) => [
          ...m,
          {
            role: 'error',
            text: `HTTP ${resp.status}: ${detail.slice(0, 400)}`,
            ts: new Date().toISOString(),
          },
        ])
      } else {
        setMessages((m) => [
          ...m,
          {
            role: 'agent',
            agent: body.agent ?? 'unknown',
            text: body.narrative ?? '(empty narrative)',
            tool_calls: body.tool_calls ?? [],
            data_as_of: body.data_as_of ?? null,
            input_tokens: body.input_tokens ?? null,
            output_tokens: body.output_tokens ?? null,
            iterations: body.iterations ?? 0,
            ts: new Date().toISOString(),
          },
        ])
      }
    } catch (e: unknown) {
      setMessages((m) => [
        ...m,
        {
          role: 'error',
          text: (e as Error).message,
          ts: new Date().toISOString(),
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="border border-paper-rule rounded-sm bg-white">
      {/* Conversation */}
      <div className="min-h-[300px] max-h-[60vh] overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="font-sans text-xs text-ink-tertiary italic">
            No messages yet. Ask a question below to start.
          </p>
        )}
        {messages.map((m, i) => {
          if (m.role === 'user') {
            return (
              <div key={i} className="flex justify-end">
                <div className="bg-teal/10 border border-teal/30 rounded-sm px-3 py-2 max-w-[80%]">
                  <div className="font-sans text-xs text-ink-primary whitespace-pre-wrap">
                    {m.text}
                  </div>
                </div>
              </div>
            )
          }
          if (m.role === 'error') {
            return (
              <div key={i} className="flex justify-start">
                <div className="bg-signal-neg/5 border border-signal-neg/30 rounded-sm px-3 py-2 max-w-[90%]">
                  <div className="font-mono text-[10px] text-signal-neg uppercase tracking-wider mb-1">
                    error
                  </div>
                  <div className="font-sans text-xs text-ink-secondary whitespace-pre-wrap">
                    {m.text}
                  </div>
                </div>
              </div>
            )
          }
          return (
            <div key={i} className="flex justify-start">
              <div className="bg-paper-rule/20 border border-paper-rule rounded-sm px-3 py-2 max-w-[90%]">
                <div className="font-mono text-[10px] text-teal mb-1">
                  {m.agent}
                </div>
                <div className="font-sans text-sm text-ink-primary whitespace-pre-wrap leading-relaxed">
                  {m.text}
                </div>
                {m.tool_calls.length > 0 && (
                  <details className="mt-2">
                    <summary className="font-sans text-[10px] text-ink-tertiary cursor-pointer hover:text-ink-secondary">
                      {m.tool_calls.length} tool call
                      {m.tool_calls.length === 1 ? '' : 's'}
                    </summary>
                    <ul className="mt-1 ml-2 space-y-0.5">
                      {m.tool_calls.map((t, ti) => (
                        <li
                          key={ti}
                          className="font-mono text-[10px] text-ink-tertiary"
                        >
                          {t.tool}({JSON.stringify(t.args).slice(0, 80)}) →{' '}
                          [{t.result_keys.join(', ').slice(0, 60)}]
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="mt-1 font-mono text-[10px] text-ink-tertiary">
                  {m.iterations} iter · in{' '}
                  {m.input_tokens ?? '—'} / out {m.output_tokens ?? '—'} tok
                  {m.data_as_of ? ` · data ${m.data_as_of}` : ''}
                </div>
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-paper-rule p-3 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <label className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
            Agent
          </label>
          <select
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            disabled={busy}
            className="font-mono text-xs border border-paper-rule rounded-sm px-2 py-1 bg-white"
          >
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <span className="ml-auto font-sans text-[10px] text-ink-tertiary">
            ⌘/Ctrl+Enter to send
          </span>
        </div>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={3}
          disabled={busy}
          placeholder="e.g. Top 5 high-conviction stocks in industry-grade tiers today"
          className="w-full border border-paper-rule rounded-sm px-2 py-1.5 font-sans text-sm text-ink-primary bg-white resize-none focus:outline-none focus:border-teal"
        />
        <button
          onClick={submit}
          disabled={busy || !input.trim()}
          className="self-end px-4 py-1.5 font-sans text-xs font-semibold rounded-sm bg-teal text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? 'Thinking…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
