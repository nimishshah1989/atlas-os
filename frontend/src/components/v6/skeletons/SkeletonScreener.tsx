// frontend/src/components/v6/skeletons/SkeletonScreener.tsx
//
// Page layout schema (implicit from eng-review; screener as a filtered stock list):
//   3 top-level children:
//     1. header strip  — eyebrow + H1 ("Screener")
//     2. body grid     — filter panel (left) + results table (right)
//     3. (no footer)
//
// Screener page — filter-based stock discovery view.

import { Shimmer } from './Shimmer'

interface SkeletonScreenerProps {
  className?: string
}

export function SkeletonScreener({ className = '' }: SkeletonScreenerProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-24" height="h-3" />
        <Shimmer width="w-36" height="h-8" />
        <Shimmer width="w-56" height="h-4" />
      </div>

      {/* 2 — body grid: filter panel + results */}
      <div className="flex gap-6">
        {/* Filter panel (left) */}
        <div className="w-56 shrink-0 space-y-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="space-y-2">
              <Shimmer width="w-24" height="h-4" />
              <Shimmer width="w-full" height="h-8" rounded="rounded" />
            </div>
          ))}
        </div>

        {/* Results table (right) */}
        <div className="flex-1 space-y-1">
          {/* Results count + sort row */}
          <div className="flex gap-4 items-center pb-2">
            <Shimmer width="w-32" height="h-4" />
            <div className="ml-auto">
              <Shimmer width="w-40" height="h-8" />
            </div>
          </div>
          {/* Header */}
          <div className="grid grid-cols-8 gap-2 pb-2 border-b border-[#C2B8A8]">
            {Array.from({ length: 8 }, (_, i) => (
              <Shimmer key={i} width="w-full" height="h-3" />
            ))}
          </div>
          {/* Rows */}
          {Array.from({ length: 12 }, (_, i) => (
            <div key={i} className="grid grid-cols-8 gap-2 py-2">
              {Array.from({ length: 8 }, (_, j) => (
                <Shimmer key={j} width="w-full" height="h-4" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
