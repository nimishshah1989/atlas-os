// /admin — operator console. Three tabs: Methodology (how the scores are built, in plain terms),
// Thresholds (edit the knobs + recompute), Data status (freshness RAG). Shared header + tab nav;
// each tab is its own route so it fetches only what it needs.
import { AdminTabNav } from '@/components/v6/admin/AdminTabNav'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1100px] px-6 py-7">
      <div className="mb-4">
        <div className="mb-2 font-num text-[11px] uppercase tracking-[0.14em] text-txt-3">
          <a href="/" className="text-brand no-underline hover:underline">Atlas</a> › Admin
        </div>
        <h1 className="font-display text-[40px] font-medium leading-[1.1] tracking-[-0.011em] text-txt-1">Admin</h1>
      </div>
      <AdminTabNav />
      {children}
    </div>
  )
}
