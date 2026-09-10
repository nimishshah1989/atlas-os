// src/app/page.tsx — the board's front door is the Pulse.
//
// The FM: "Even for the pulse page, we have all three: pulse, sector, and theme, which gives
// everything combined… If you look at Atlas today, that is what we call pulse."
//
// It used to redirect to Countries, from an earlier decision made when the Pulse was breadth bars
// and nothing else — a front door full of placeholders is worse than no front door, and Countries
// was the only page with something to say. The Pulse now summarises every board and links into
// each of them, so it has earned the slot back. Countries keeps its own section.
//
// A redirect rather than a copy: two routes rendering the same queries would be two places to
// keep in step, and /pulse already owns that job.
import { redirect } from 'next/navigation'

export default async function HomePage() {
  redirect('/pulse')
}
