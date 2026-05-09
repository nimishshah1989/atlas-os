// src/app/admin/thresholds/page.tsx
// Backward-compat redirect — /admin/thresholds now lives at /admin/policies.
// Keeps any bookmarked /admin/thresholds URLs working.
import { redirect } from 'next/navigation'

export default function ThresholdsRedirect() {
  redirect('/admin/policies?tab=advanced')
}
