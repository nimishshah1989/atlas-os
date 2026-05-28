// frontend/src/app/calls/loading.tsx
//
// Skeleton loading state for /calls (Page 08 — Calls Performance).
// Shown by Next.js App Router while the RSC shell fetches data.

export default function CallsLoading() {
  return (
    <div className="min-h-screen bg-paper animate-pulse">
      {/* Page header skeleton */}
      <section className="py-8 border-b border-paper-rule">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="h-3 w-40 bg-paper-deep rounded mb-3" />
          <div className="h-12 w-96 bg-paper-deep rounded mb-4" />
          <div className="h-4 w-[600px] bg-paper-deep rounded" />
          {/* Hero tiles skeleton */}
          <div className="grid grid-cols-6 gap-0 border border-paper-rule rounded-[2px] mt-6 overflow-hidden">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className={`px-[18px] py-[14px] ${i < 5 ? 'border-r border-paper-rule' : ''}`}>
                <div className="h-2 w-20 bg-paper-deep rounded mb-2" />
                <div className="h-7 w-16 bg-paper-deep rounded mb-1" />
                <div className="h-2 w-24 bg-paper-deep rounded" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Matrix skeleton */}
      <section className="py-9 border-b border-paper-rule">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="h-7 w-64 bg-paper-deep rounded mb-4" />
          <div className="h-[260px] bg-paper-deep rounded-[2px]" />
        </div>
      </section>

      {/* Trajectories skeleton */}
      <section className="py-9 border-b border-paper-rule">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="h-7 w-64 bg-paper-deep rounded mb-4" />
          <div className="h-[280px] bg-paper-deep rounded-[2px]" />
        </div>
      </section>

      {/* Cards skeleton */}
      <section className="py-9 border-b border-paper-rule">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="h-7 w-48 bg-paper-deep rounded mb-4" />
          <div className="grid grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-[220px] bg-paper-deep rounded-[2px]" />
            ))}
          </div>
        </div>
      </section>

      {/* Table skeleton */}
      <section className="py-9">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="h-7 w-56 bg-paper-deep rounded mb-4" />
          <div className="h-[400px] bg-paper-deep rounded-[2px]" />
        </div>
      </section>
    </div>
  )
}
