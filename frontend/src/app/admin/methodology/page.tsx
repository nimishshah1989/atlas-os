// The methodology now lives on ONE public page (/methodology) — the visual lens mind-map, the
// full expandable tree, and the live weights + thresholds, all in one place. This admin route is
// kept only as a redirect so old links still land somewhere sensible.
import { redirect } from 'next/navigation'

export default function AdminMethodologyPage() {
  redirect('/methodology')
}
