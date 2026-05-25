// frontend/src/components/v6/skeletons/SkeletonSectors.tsx
//
// Page layout schema (design-application.md §6.7):
//   4 top-level children:
//     1. header strip  — eyebrow + H1 ("Today's sector map")
//     2. industry overview  — rotating in/out + breadth
//     3. charts section     — RRG + bubble chart
//     4. ranked ladder      — 30-row sector table
//
// Sector list page.

import { Shimmer } from './Shimmer'

interface SkeletonSectorsProps {
  className?: string
}

export function SkeletonSectors({ className = '' }: SkeletonSectorsProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-32" height="h-3" />
        <Shimmer width="w-56" height="h-8" />
      </div>

      {/* 2 — industry overview callouts */}
      <div className="grid grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-2">
            <Shimmer width="w-24" height="h-3" />
            <Shimmer width="w-full" height="h-6" />
            <Shimmer width="w-2/3" height="h-3" />
          </div>
        ))}
      </div>

      {/* 3 — charts section */}
      <div className="grid grid-cols-2 gap-4">
        <Shimmer width="w-full" height="h-64" rounded="rounded-lg" />
        <Shimmer width="w-full" height="h-64" rounded="rounded-lg" />
      </div>

      {/* 4 — ranked ladder */}
      <div className="space-y-1">
        <div className="grid grid-cols-5 gap-2 pb-2 border-b border-[#C2B8A8]">
          {Array.from({ length: 5 }, (_, i) => (
            <Shimmer key={i} width="w-full" height="h-3" />
          ))}
        </div>
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="grid grid-cols-5 gap-2 py-2">
            {Array.from({ length: 5 }, (_, j) => (
              <Shimmer key={j} width="w-full" height="h-4" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
