// src/app/page.tsx — the board's front door is the country grid (the FM's decision D1 of
// 2026-09-09: "Global gets one tab, and it is Countries").
//
// A redirect rather than a copy of the grid: two routes rendering the same query would be two
// places to keep in step, and the country page already owns that job. A Today page earns this
// slot back when there is a day's worth of scored movement to put on it — not before, because
// a front door full of placeholders is worse than no front door.
import { redirect } from 'next/navigation'

export default async function HomePage() {
  redirect('/countries')
}
