export const revalidate = 300

import { EngineRoom } from '@/components/desk/EngineRoom'

export const metadata = { title: 'Engine Room · Atlas Desk' }

export default async function EngineRoomPage({
  searchParams,
}: {
  searchParams: Promise<{ desk?: string; date?: string }>
}) {
  const { desk, date } = await searchParams
  return <EngineRoom desk={desk} date={date} />
}
