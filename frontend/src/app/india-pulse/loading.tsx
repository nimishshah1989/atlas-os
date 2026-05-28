// frontend/src/app/india-pulse/loading.tsx
// Skeleton loading state for India Pulse page

export default function IndiaPulseLoading() {
  return (
    <div className="min-h-screen bg-paper animate-pulse">
      {/* Page header skeleton */}
      <div className="border-b border-paper-rule px-8 py-8">
        <div className="max-w-[1400px] mx-auto">
          <div className="h-3 w-24 bg-paper-deep rounded mb-4" />
          <div className="h-10 w-72 bg-paper-deep rounded mb-3" />
          <div className="h-4 w-[560px] bg-paper-deep rounded" />
          {/* Hero strip skeleton */}
          <div className="mt-6 grid grid-cols-4 border border-paper-rule rounded-sm overflow-hidden">
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="p-5 border-r border-paper-rule last:border-r-0">
                <div className="h-2 w-24 bg-paper-deep rounded mb-3" />
                <div className="h-8 w-16 bg-paper-deep rounded mb-2" />
                <div className="h-3 w-full bg-paper-deep rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Section skeletons */}
      {[1, 2, 3].map(i => (
        <div key={i} className="border-b border-paper-rule px-8 py-10">
          <div className="max-w-[1400px] mx-auto">
            <div className="h-7 w-48 bg-paper-deep rounded mb-4" />
            <div className="grid grid-cols-4 gap-3">
              {[0, 1, 2, 3].map(j => (
                <div key={j} className="h-40 bg-paper-deep rounded-sm" />
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
