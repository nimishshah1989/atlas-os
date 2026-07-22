export const revalidate = 300

import { TodayBoard } from '@/components/today/TodayBoard'

export const metadata = { title: 'Today · Atlas' }

export default function TodayPage() {
  return <TodayBoard />
}
