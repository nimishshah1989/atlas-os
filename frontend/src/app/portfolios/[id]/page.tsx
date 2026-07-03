export const revalidate = 300

import { PortfolioDetailV4 } from '@/components/portfolios/PortfolioDetailV4'

export const metadata = { title: 'Portfolio · Atlas' }

export default async function PortfolioDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <PortfolioDetailV4 id={id} />
}
