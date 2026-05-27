// frontend/src/app/markets-rs/page.tsx
//
// RSC shell for /markets-rs (Page 03 — Markets Relative Strength).
// Thin shell ≤250 LOC — all rendering in MarketsRsClient.tsx.
//
// Route: /markets-rs (root, per spec D4 — no /v6/ prefix on new routes)

import type { Metadata } from 'next'
import { getMarketsRsPage } from '@/lib/queries/v6/markets_rs'
import { MarketsRsClient } from '@/components/v6/MarketsRsClient'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export const metadata: Metadata = {
  title: 'Markets RS · Atlas',
  description: 'Relative strength grid — 9 baselines × 5 windows. India vs world, within India breakdown.',
  robots: 'noindex, nofollow',
}

export default async function MarketsRsPage() {
  const data = await getMarketsRsPage()
  return <MarketsRsClient data={data} />
}
