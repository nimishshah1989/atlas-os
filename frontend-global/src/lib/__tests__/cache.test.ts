// The board must be correct by default: a cached page has a MAXIMUM AGE, not only a tag.
//
// The tag alone was the whole publish path, and it depended on GLOBAL_REVALIDATE_URL and
// GLOBAL_REVALIDATE_SECRET being set on the box and the same secret on the deployment. On
// 2026-09-10 none of that had ever been configured, so the webhook had never fired and
// `unstable_cache` with a tag and no age cached indefinitely: the board served week-old numbers
// while the nightly wrote fresh ones, and the only evidence was one skipped step in a log on the
// box. Nothing on the board, in CI, or in any gate could see it.
//
// This test is what can see it. Deleting the `revalidate` option is a one-word edit whose only
// symptom is a board that silently stops moving — the exact failure it took a week to notice.
import { describe, expect, it, vi } from 'vitest'

const calls: { keys: string[]; options: unknown }[] = []

vi.mock('next/cache', () => ({
  unstable_cache: (fn: unknown, keys: string[], options: unknown) => {
    calls.push({ keys, options })
    return fn
  },
}))

describe('eodCached', () => {
  it('caches under the eod tag AND a maximum age, so a missing publish cannot freeze the board', async () => {
    const { eodCached, EOD_MAX_AGE_SECONDS } = await import('@/lib/cache')
    const { TAG } = await import('@/lib/revalidate')

    eodCached(async () => 'rows', 'sectors')

    expect(calls).toHaveLength(1)
    expect(calls[0].keys).toEqual(['sectors'])
    expect(calls[0].options).toEqual({ tags: [TAG], revalidate: EOD_MAX_AGE_SECONDS })
  })

  it('bounds the staleness a reader can see to something a person would accept', async () => {
    const { EOD_MAX_AGE_SECONDS } = await import('@/lib/cache')

    // Not a methodology number: no score depends on it. But it has to be a real bound — an hour
    // is too long to wait to see a nightly that finished, and a minute would re-run every query
    // on the board all day for data that changes once.
    expect(EOD_MAX_AGE_SECONDS).toBeGreaterThanOrEqual(60)
    expect(EOD_MAX_AGE_SECONDS).toBeLessThanOrEqual(1800)
  })
})
