// frontend/src/app/india-pulse/page.tsx
//
// RSC shell for /india-pulse (Page 02 — India Pulse).
// Thin shell ≤250 LOC — all rendering in IndiaPulseClient.tsx.
//
// Route: /india-pulse (root, per spec D4 — no /v6/ prefix on new routes)

import type { Metadata } from 'next'
import { getIndiaPulsePage } from '@/lib/queries/v6/india_pulse'
import { IndiaPulseClient } from '@/components/v6/india-pulse/IndiaPulseClient'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export const metadata: Metadata = {
  title: 'India Pulse · Atlas',
  description:
    'The four regime inputs — breadth, volatility, dispersion, tier leadership — plus macro context for the full India market read.',
  robots: 'noindex, nofollow',
}

export default async function IndiaPulsePage() {
  const data = await getIndiaPulsePage()
  return <IndiaPulseClient data={data} />
}
