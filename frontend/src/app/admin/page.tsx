import { redirect } from 'next/navigation'

export default function AdminIndex() {
  // Methodology moved to the public /methodology page; land on the first real admin tab.
  redirect('/admin/thresholds')
}
