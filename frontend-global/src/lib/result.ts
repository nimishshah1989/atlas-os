// src/lib/result.ts — a query outcome the page can render honestly: the rows, or what failed.
//
// A HANG IS NOT AN ERROR, and that is the whole reason `timeoutMs` exists. try/catch sees a
// rejection; it never sees a promise that simply does not settle. /health on the box answered
// 0 bytes in 25 seconds for a day while every one of its queries ran in under 0.1s when tried
// one at a time — a page with no budget on its awaits cannot even say which of them stalled.
// With a budget, the stall becomes a named error the page renders, and the reader learns the
// query, not just the silence.
//
// The budget does NOT cancel anything: postgres.js has no cancel for a queued query, so the
// statement keeps running server-side and its connection stays held until it returns or the
// pool recycles it. The page stops waiting; the database does not. The message says so.

export type Result<T> = { ok: true; value: T } | { ok: false; error: string }

export type AttemptOptions = {
  /** Named in the timeout message so the reader knows WHICH await stalled. */
  label?: string
  /** Settle-or-fail budget. Undefined = wait forever, the pre-2026-09-08 behaviour. */
  timeoutMs?: number
}

function withBudget<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(
      () =>
        reject(
          new Error(
            `${label} did not answer within ${ms / 1000}s — the query is still running server-side; ` +
              'nothing was cancelled. See src/lib/result.ts.',
          ),
        ),
      ms,
    )
    p.then(
      (v) => {
        clearTimeout(timer)
        resolve(v)
      },
      (e) => {
        clearTimeout(timer)
        reject(e)
      },
    )
  })
}

export async function attempt<T>(p: Promise<T>, opts: AttemptOptions = {}): Promise<Result<T>> {
  const { label = 'query', timeoutMs } = opts
  try {
    const value = timeoutMs === undefined ? await p : await withBudget(p, timeoutMs, label)
    return { ok: true, value }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}
