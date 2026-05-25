// frontend/src/components/v6/skeletons/SkeletonStocks.tsx
//
// Page layout schema (design-application.md §6.3):
//   3 top-level children:
//     1. header strip  — eyebrow + H1 + subhead
//     2. body grid     — filter row + bubble chart + ranked table
//     3. (table is part of body section)
//
// Stock universe list page.

import { Shimmer } from './Shimmer'

interface SkeletonStocksProps {
  className?: string
}

export function SkeletonStocks({ className = '' }: SkeletonStocksProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-36" height="h-3" />
        <Shimmer width="w-64" height="h-8" />
        <Shimmer width="w-80" height="h-4" />
      </div>

      {/* 2 — body grid */}
      <div className="space-y-4">
        {/* Filter row + toggles */}
        <div className="flex gap-2 flex-wrap">
          {[0, 1, 2, 3, 4].map((i) => (
            <Shimmer key={i} width="w-20" height="h-8" rounded="rounded-full" />
          ))}
          <div className="ml-auto flex gap-2">
            <Shimmer width="w-48" height="h-8" />
            <Shimmer width="w-56" height="h-8" />
          </div>
        </div>

        {/* Bubble chart area */}
        <Shimmer width="w-full" height="h-64" rounded="rounded-lg" />

        {/* Ranked table */}
        <div className="space-y-1">
          {/* Table header */}
          <div className="grid grid-cols-9 gap-2 pb-2 border-b border-[#C2B8A8]">
            {Array.from({ length: 9 }, (_, i) => (
              <Shimmer key={i} width="w-full" height="h-3" />
            ))}
          </div>
          {/* Table rows */}
          {Array.from({ length: 10 }, (_, i) => (
            <div key={i} className="grid grid-cols-9 gap-2 py-2">
              {Array.from({ length: 9 }, (_, j) => (
                <Shimmer key={j} width="w-full" height="h-4" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
