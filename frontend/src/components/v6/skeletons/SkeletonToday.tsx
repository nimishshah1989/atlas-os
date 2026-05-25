// frontend/src/components/v6/skeletons/SkeletonToday.tsx
//
// Page layout schema (design-application.md §6.2):
//   3 top-level children:
//     1. header strip  — eyebrow + H1
//     2. body grid     — 3-col card row + sector ladder + signal calls list
//     3. (no distinct footer)
//
// Three-column responsive grid above the ladder.

import { Shimmer } from './Shimmer'

interface SkeletonTodayProps {
  className?: string
}

export function SkeletonToday({ className = '' }: SkeletonTodayProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-32" height="h-3" />
        <Shimmer width="w-48" height="h-8" />
      </div>

      {/* 2 — body grid */}
      <div className="space-y-6">
        {/* 3-column hero cards */}
        <div className="grid grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-3">
              <Shimmer width="w-2/3" height="h-4" />
              <Shimmer width="w-full" height="h-24" />
              <Shimmer width="w-1/2" height="h-3" />
            </div>
          ))}
        </div>

        {/* Sector ladder snapshot */}
        <div className="space-y-2">
          <Shimmer width="w-40" height="h-4" />
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="flex gap-4 items-center">
              <Shimmer width="w-6" height="h-4" />
              <Shimmer width="w-32" height="h-4" />
              <Shimmer width="w-24" height="h-4" />
              <Shimmer width="w-16" height="h-4" />
            </div>
          ))}
        </div>

        {/* Recent signal calls */}
        <div className="space-y-2">
          <Shimmer width="w-48" height="h-4" />
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="flex gap-4 items-center">
              <Shimmer width="w-20" height="h-4" />
              <Shimmer width="w-64" height="h-4" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
