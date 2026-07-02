export const revalidate = 300

import { SectorDeepDiveV4 } from '@/components/sectors/SectorDeepDiveV4'

export default async function SectorDetailPage({ params }: { params: Promise<{ sector: string }> }) {
  const decoded = decodeURIComponent((await params).sector)
  return <SectorDeepDiveV4 sector={decoded} />
}
