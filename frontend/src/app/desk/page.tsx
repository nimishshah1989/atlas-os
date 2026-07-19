export const revalidate = 300

import { DeskBoardV1 } from '@/components/desk/DeskBoardV1'

export const metadata = { title: 'The Desk · Atlas' }

export default function DeskPage() {
  return <DeskBoardV1 />
}
