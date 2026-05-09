export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-paper min-h-screen">
      <div className="border-b border-paper-rule px-8 py-3">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wider">
          Atlas-OS · Admin
        </p>
      </div>
      {children}
    </div>
  )
}
