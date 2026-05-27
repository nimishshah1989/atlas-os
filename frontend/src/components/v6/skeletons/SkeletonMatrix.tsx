// frontend/src/components/v6/skeletons/SkeletonMatrix.tsx
//
// Page layout schema (design-application.md §6.1):
//   3 top-level children:
//     1. header strip  — eyebrow + H1 + subhead
//     2. body grid     — 3 rows × 8 columns (24 tiles)
//     3. footer        — methodology link + stats
//
// Each skeleton mirrors this structure at the gross layout level.
// No async, no external imports beyond Shimmer.

import { Shimmer } from './Shimmer'

interface SkeletonMatrixProps {
  className?: string
}

export function SkeletonMatrix({ className = '' }: SkeletonMatrixProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-40" height="h-3" />
        <Shimmer width="w-56" height="h-8" />
        <Shimmer width="w-72" height="h-4" />
      </div>

      {/* 2 — 24-cell grid (3 rows × 8 cols) */}
      <div className="space-y-3">
        {[0, 1, 2].map((row) => (
          <div key={row} className="grid grid-cols-8 gap-3">
            {Array.from({ length: 8 }, (_, col) => (
              <div key={col} className="space-y-2 p-3 border border-[#C2B8A8] rounded">
                <Shimmer width="w-full" height="h-3" />
                <Shimmer width="w-3/4" height="h-4" />
                <Shimmer width="w-full" height="h-3" />
                <Shimmer width="w-2/3" height="h-3" />
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* 3 — footer */}
      <div className="flex gap-4">
        <Shimmer width="w-48" height="h-4" />
        <Shimmer width="w-64" height="h-4" />
      </div>
    </div>
  )
}
