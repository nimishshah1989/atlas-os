// attempt() with a budget turns a promise that never settles into a NAMED error. No fixture,
// no data: the thing under test is a promise, and the assertion is about time and a string.
import { describe, expect, it } from 'vitest'
import { attempt } from '@/lib/result'

const never = () => new Promise<number>(() => {})

describe('attempt with timeoutMs', () => {
  it('turns a promise that never settles into ok:false naming the label and the budget', async () => {
    const r = await attempt(never(), { label: 'provider calls', timeoutMs: 20 })
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.error).toMatch(/^provider calls did not answer within 0\.02s/)
      expect(r.error).toMatch(/nothing was cancelled/)
    }
  })

  it('returns the value untouched when the promise settles inside the budget', async () => {
    const r = await attempt(Promise.resolve(41 + 1), { label: 'fast', timeoutMs: 1000 })
    expect(r).toEqual({ ok: true, value: 42 })
  })

  it('still reports a rejection as before, budget or not', async () => {
    const r = await attempt(Promise.reject(new Error('boom')), { timeoutMs: 1000 })
    expect(r).toEqual({ ok: false, error: 'boom' })
  })

  it('without a budget waits — the pre-existing contract every other page relies on', async () => {
    let settled = false
    const p = new Promise<string>((resolve) => setTimeout(() => { settled = true; resolve('late') }, 30))
    const r = await attempt(p)
    expect(settled).toBe(true)
    expect(r).toEqual({ ok: true, value: 'late' })
  })
})
