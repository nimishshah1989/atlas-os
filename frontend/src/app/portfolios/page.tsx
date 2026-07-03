export const revalidate = 300

import { PortfoliosPageV4 } from '@/components/portfolios/PortfoliosPageV4'

export const metadata = { title: 'Portfolios · Atlas' }

export default function PortfoliosPage() {
  return <PortfoliosPageV4 />
}
