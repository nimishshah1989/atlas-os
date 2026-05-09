// src/app/loading.tsx
export default function Loading() {
  return (
    <div className="p-8 max-w-5xl mx-auto animate-pulse">
      <div className="h-12 bg-paper-rule/40 rounded w-64 mb-4" />
      <div className="h-4 bg-paper-rule/40 rounded w-96 mb-2" />
      <div className="h-4 bg-paper-rule/40 rounded w-80" />
    </div>
  )
}
