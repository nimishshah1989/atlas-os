export const revalidate = 300

import { ETFDetailV4 } from '@/components/v6/etfs/ETFDetailV4'

export default async function ETFDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const decoded = decodeURIComponent((await params).ticker)
  return <ETFDetailV4 fcode={decoded} />
}
