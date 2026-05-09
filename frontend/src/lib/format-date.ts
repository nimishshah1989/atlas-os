// Format a date as DD-MMM-YYYY [HH:mm IST] per ~/.claude/rules/frontend-viz.md.
// All three components are derived in the Asia/Kolkata zone so a UTC timestamp
// near midnight does not produce a mixed UTC-day + IST-month display.

const IST: Intl.DateTimeFormatOptions = { timeZone: 'Asia/Kolkata' }

export function formatIST(d: Date | string, withTime: boolean = false): string {
  const date = typeof d === 'string' ? new Date(d) : d
  const day = new Intl.DateTimeFormat('en-IN', { ...IST, day: '2-digit' }).format(date)
  const month = new Intl.DateTimeFormat('en-IN', { ...IST, month: 'short' }).format(date)
  const year = new Intl.DateTimeFormat('en-IN', { ...IST, year: 'numeric' }).format(date)
  if (!withTime) return `${day}-${month}-${year}`
  const time = new Intl.DateTimeFormat('en-IN', {
    ...IST, hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
  return `${day}-${month}-${year} ${time} IST`
}
