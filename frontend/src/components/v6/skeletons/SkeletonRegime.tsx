// frontend/src/components/v6/skeletons/SkeletonRegime.tsx
//
// Page layout schema (design-application.md §6.9):
//   3 top-level children:
//     1. header strip — large regime label + sentence + 12-week journey strip
//     2. body sections — breadth gauge + vol + cross-sector + favored cells
//     3. regime classifier explainer
//
// Market regime page.

import { Shimmer } from './Shimmer'

interface SkeletonRegimeProps {
  className?: string
}

export function SkeletonRegime({ className = '' }: SkeletonRegimeProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-3">
        <Shimmer width="w-64" height="h-12" />
        <Shimmer width="w-96" height="h-5" />
        {/* 12-week journey strip */}
        <div className="flex gap-1">
          {Array.from({ length: 12 }, (_, i) => (
            <Shimmer key={i} width="w-full" height="h-10" rounded="rounded" />
          ))}
        </div>
      </div>

      {/* 2 — body sections */}
      <div className="space-y-4">
        {/* Breadth gauges + vol */}
        <div className="grid grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-2">
              <Shimmer width="w-32" height="h-4" />
              <Shimmer width="w-full" height="h-16" rounded="rounded-lg" />
              <Shimmer width="w-20" height="h-4" />
            </div>
          ))}
        </div>

        {/* Favored cells list */}
        <div className="space-y-2">
          <Shimmer width="w-56" height="h-4" />
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex gap-4 items-center">
              <Shimmer width="w-40" height="h-6" rounded="rounded-full" />
              <Shimmer width="w-64" height="h-4" />
            </div>
          ))}
        </div>
      </div>

      {/* 3 — classifier explainer */}
      <div className="border border-[#C2B8A8] rounded p-4 space-y-2">
        <Shimmer width="w-48" height="h-4" />
        <Shimmer width="w-full" height="h-4" />
        <Shimmer width="w-5/6" height="h-4" />
      </div>
    </div>
  )
}
