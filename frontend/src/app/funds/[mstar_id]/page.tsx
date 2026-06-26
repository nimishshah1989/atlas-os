export const revalidate = 300

import { FundDetailV4 } from '@/components/v6/funds/FundDetailV4'

export default async function FundDetailPage({ params }: { params: Promise<{ mstar_id: string }> }) {
  const { mstar_id } = await params
  return <FundDetailV4 mstarId={mstar_id} />
}
