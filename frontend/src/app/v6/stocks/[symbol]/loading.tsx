export default function Loading() {
  return (
    <div className="container mx-auto px-8 py-16">
      <div className="animate-pulse">
        <div className="h-8 w-24 bg-paper-deep rounded mb-4" />
        <div className="h-12 w-3/4 bg-paper-deep rounded mb-8" />
        <div className="grid grid-cols-4 gap-4 mb-12">
          <div className="h-32 bg-paper-deep rounded" />
          <div className="h-32 bg-paper-deep rounded" />
          <div className="h-32 bg-paper-deep rounded" />
          <div className="h-32 bg-paper-deep rounded" />
        </div>
        <div className="h-64 bg-paper-deep rounded mb-8" />
        <div className="grid grid-cols-2 gap-6">
          <div className="h-48 bg-paper-deep rounded" />
          <div className="h-48 bg-paper-deep rounded" />
        </div>
      </div>
    </div>
  )
}
