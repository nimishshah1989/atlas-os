export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-surface-base min-h-screen">
      <div className="border-b border-edge-hair px-8 py-3">
        <p className="font-num text-xs text-txt-3 uppercase tracking-wider">
          Atlas-OS · Admin
        </p>
      </div>
      {children}
    </div>
  )
}
