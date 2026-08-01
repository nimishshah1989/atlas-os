'use client'
// Download PDF = the browser's own print-to-PDF against the report stylesheet.
// No PDF dependency, and the layout is exactly what is on screen.
export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="rounded-tile border border-brand/40 bg-brand/10 px-4 py-2 font-sans text-[13px] font-semibold text-brand hover:bg-brand/15"
    >
      Download PDF
    </button>
  )
}
