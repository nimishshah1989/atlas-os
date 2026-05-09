'use client'
type Props = { sectorName: string; range: string; onClose: () => void }
export function SectorDrawer({ sectorName, onClose }: Props) {
  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-[480px] bg-paper border-l border-paper-rule z-50 overflow-y-auto shadow-xl">
        <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between">
          <h2 className="font-sans text-sm font-semibold text-ink-primary">{sectorName}</h2>
          <button onClick={onClose} className="text-ink-tertiary hover:text-ink-primary text-xs">✕</button>
        </div>
        <div className="p-6 text-ink-tertiary text-xs">Loading sector detail...</div>
      </div>
    </>
  )
}
