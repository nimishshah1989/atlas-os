// frontend/src/components/v6/skeletons/SkeletonStockDetail.tsx
//
// Page layout schema (design-application.md §6.4):
//   3 top-level children:
//     1. header strip  — hero with name + grade chip + conviction tape + thesis
//     2. body grid     — tab nav + tab content (Overview charts + tables)
//     3. (no footer)
//
// Stock detail page — deepest page in the app.

import { Shimmer } from './Shimmer'

interface SkeletonStockDetailProps {
  className?: string
}

export function SkeletonStockDetail({ className = '' }: SkeletonStockDetailProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — hero header strip */}
      <div className="space-y-3 pb-4 border-b border-[#C2B8A8]">
        <div className="flex items-start justify-between">
          <div className="space-y-2 flex-1">
            <Shimmer width="w-72" height="h-8" />
            <Shimmer width="w-56" height="h-4" />
          </div>
          <Shimmer width="w-16" height="h-8" rounded="rounded" />
        </div>
        {/* Toggles */}
        <div className="flex gap-2">
          <Shimmer width="w-48" height="h-8" />
          <Shimmer width="w-56" height="h-8" />
        </div>
        {/* Conviction tape */}
        <Shimmer width="w-full" height="h-8" rounded="rounded" />
        {/* Thesis bullets */}
        <div className="space-y-2">
          <Shimmer width="w-48" height="h-5" />
          {Array.from({ length: 4 }, (_, i) => (
            <Shimmer key={i} width={i % 2 === 0 ? 'w-full' : 'w-5/6'} height="h-4" />
          ))}
        </div>
      </div>

      {/* 2 — body grid: tabs + content */}
      <div className="space-y-4">
        {/* Tab nav */}
        <div className="flex gap-6 border-b border-[#C2B8A8]">
          {[0, 1, 2, 3].map((i) => (
            <Shimmer key={i} width="w-20" height="h-8" />
          ))}
        </div>
        {/* Tab content — waterfall + charts */}
        <Shimmer width="w-full" height="h-48" rounded="rounded-lg" />
        <div className="grid grid-cols-2 gap-4">
          <Shimmer width="w-full" height="h-48" rounded="rounded-lg" />
          <Shimmer width="w-full" height="h-48" rounded="rounded-lg" />
        </div>
      </div>
    </div>
  )
}
