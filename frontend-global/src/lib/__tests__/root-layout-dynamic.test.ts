// The root layout renders every route on request. This pins that decision, because the day it
// silently stops being true the build fails on the box and nowhere else:
//
//   ⨯ useSearchParams() should be wrapped in a suspense boundary at page "/stocks"
//
// is a static-PRERENDER error. It needs a real, populated database to mount the explorer, so no
// local `next build` and no CI job can reproduce it — the 2026-09-08 deploy did, twice, after
// the board opened and requireUser() stopped redirecting (a redirect had been what kept every
// route dynamic). Read as text rather than imported: importing layout.tsx drags next/font into
// vitest, and the thing being asserted is a literal.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const LAYOUT = resolve(__dirname, '../../app/layout.tsx')

describe('root layout', () => {
  it("exports dynamic = 'force-dynamic', so no route is prerendered at build time", () => {
    const src = readFileSync(LAYOUT, 'utf8')
    expect(src).toMatch(/^export const dynamic = 'force-dynamic'$/m)
  })

  it('does not also opt into static generation, which would contradict the line above', () => {
    const src = readFileSync(LAYOUT, 'utf8')
    expect(src).not.toMatch(/export const dynamic = 'force-static'|generateStaticParams|export const revalidate/)
  })
})
