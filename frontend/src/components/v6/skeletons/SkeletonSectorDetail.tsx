// frontend/src/components/v6/skeletons/SkeletonSectorDetail.tsx
//
// Page layout schema (design-application.md §6.8):
//   3 top-level children:
//     1. header strip  — sector name + rank + conviction tape + action verb
//     2. body sections — SectorBreadthPanel + bubble + constituent table
//     3. (no footer)
//
// Sector detail page.

import { Shimmer } from './Shimmer'

interface SkeletonSectorDetailProps {
  className?: string
}

export function SkeletonSectorDetail({ className = '' }: SkeletonSectorDetailProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2 pb-4 border-b border-[#C2B8A8]">
        <Shimmer width="w-28" height="h-3" />
        <div className="flex items-center justify-between">
          <Shimmer width="w-48" height="h-8" />
          <Shimmer width="w-20" height="h-8" />
        </div>
        <Shimmer width="w-full" height="h-8" rounded="rounded" />
        <Shimmer width="w-64" height="h-5" />
      </div>

      {/* 2 — body sections */}
      <div className="space-y-6">
        {/* SectorBreadthPanel: 3 gauge bars */}
        <div className="space-y-2">
          <Shimmer width="w-40" height="h-4" />
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-4">
              <Shimmer width="w-28" height="h-4" />
              <Shimmer width="w-48" height="h-6" />
              <Shimmer width="w-16" height="h-4" />
            </div>
          ))}
          <Shimmer width="w-72" height="h-5" rounded="rounded-full" />
        </div>

        {/* Bubble chart */}
        <Shimmer width="w-full" height="h-56" rounded="rounded-lg" />

        {/* Constituent table */}
        <div className="space-y-1">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="grid grid-cols-6 gap-2 py-2">
              {Array.from({ length: 6 }, (_, j) => (
                <Shimmer key={j} width="w-full" height="h-4" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
