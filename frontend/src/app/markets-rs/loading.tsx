// frontend/src/app/markets-rs/loading.tsx
//
// Skeleton for /markets-rs — shown while RSC data fetch is in flight.
// Paper-deep placeholder blocks in 4-card + table + chart-grid shape.

export default function MarketsRsLoading() {
  return (
    <div className="max-w-[1400px] mx-auto animate-pulse">
      {/* Page head skeleton */}
      <div className="px-8 pt-8 pb-6" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div className="h-3 w-24 rounded-sm mb-3" style={{ background: 'var(--color-paper-rule)' }} />
        <div className="h-10 w-96 rounded-sm mb-3" style={{ background: 'var(--color-paper-rule)' }} />
        <div className="h-4 w-full max-w-2xl rounded-sm mb-2" style={{ background: 'var(--color-paper-deep)' }} />
        <div className="h-4 w-3/4 max-w-xl rounded-sm" style={{ background: 'var(--color-paper-deep)' }} />
      </div>

      {/* 4-card hero skeleton */}
      <div className="px-8 py-6" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div
          className="grid grid-cols-4"
          style={{ border: '1px solid var(--color-paper-rule)', borderRadius: '2px', background: 'var(--color-paper-deep)' }}
        >
          {[0, 1, 2, 3].map(i => (
            <div
              key={i}
              className="px-6 py-5"
              style={{ borderRight: i < 3 ? '1px solid var(--color-paper-rule)' : 'none' }}
            >
              <div className="h-2 w-20 rounded-sm mb-3" style={{ background: 'var(--color-paper-rule)' }} />
              <div className="h-6 w-40 rounded-sm mb-2" style={{ background: 'var(--color-paper-rule)' }} />
              <div className="h-3 w-32 rounded-sm" style={{ background: 'var(--color-paper-deep)' }} />
            </div>
          ))}
        </div>
      </div>

      {/* RS grid skeleton */}
      <div className="px-8 py-10" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div className="h-7 w-64 rounded-sm mb-3" style={{ background: 'var(--color-paper-rule)' }} />
        <div className="h-3 w-full max-w-xl rounded-sm mb-5" style={{ background: 'var(--color-paper-deep)' }} />
        <div style={{ border: '1px solid var(--color-paper-rule)', borderRadius: '2px', overflow: 'hidden' }}>
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(i => (
            <div
              key={i}
              className="flex gap-2 px-4 py-3"
              style={{ borderBottom: i < 10 ? '1px solid var(--color-paper-rule)' : 'none', background: i % 4 === 0 ? 'var(--color-paper-deep)' : 'var(--color-paper)' }}
            >
              <div className="h-4 w-40 rounded-sm" style={{ background: 'var(--color-paper-rule)' }} />
              {[0, 1, 2, 3, 4].map(j => (
                <div key={j} className="h-10 flex-1 rounded-sm" style={{ background: 'var(--color-paper-deep)' }} />
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Narrative skeleton */}
      <div className="px-8 py-10" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div className="h-7 w-56 rounded-sm mb-5" style={{ background: 'var(--color-paper-rule)' }} />
        <div style={{ border: '1px solid var(--color-paper-rule)', borderRadius: '2px', padding: '24px' }}>
          {[0, 1, 2, 3, 4].map(i => (
            <div key={i} className="flex gap-4 mb-4">
              <div className="h-6 w-16 rounded-sm" style={{ background: 'var(--color-paper-rule)' }} />
              <div className="flex-1 h-4 rounded-sm" style={{ background: 'var(--color-paper-deep)' }} />
            </div>
          ))}
        </div>
      </div>

      {/* Chart grid skeleton */}
      <div className="px-8 py-10">
        <div className="h-7 w-96 rounded-sm mb-5" style={{ background: 'var(--color-paper-rule)' }} />
        <div className="grid grid-cols-2 gap-4">
          {[0, 1, 2, 3, 4, 5].map(i => (
            <div
              key={i}
              style={{ border: '1px solid var(--color-paper-rule)', borderRadius: '2px', padding: '20px' }}
            >
              <div className="h-5 w-48 rounded-sm mb-2" style={{ background: 'var(--color-paper-rule)' }} />
              <div className="h-3 w-36 rounded-sm mb-3" style={{ background: 'var(--color-paper-deep)' }} />
              <div className="w-full rounded-sm" style={{ height: '300px', background: 'var(--color-paper-deep)' }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
