export const revalidate = 300

import { TodayBoard } from '@/components/today/TodayBoard'

export const metadata = { title: 'Movers & Shakers · Atlas' }

export default function TodayPage() {
  return <TodayBoard />
}
