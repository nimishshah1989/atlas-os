export function formatIST(d: Date | string, withTime: boolean = false): string {
  const date = typeof d === 'string' ? new Date(d) : d
  const day = String(date.getUTCDate()).padStart(2, '0')
  const month = date.toLocaleString('en-IN', { month: 'short', timeZone: 'Asia/Kolkata' })
  const year = date.getFullYear()
  if (!withTime) return `${day}-${month}-${year}`
  // Render time in IST
  const istString = new Intl.DateTimeFormat('en-IN', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata',
  }).format(date)
  return `${day}-${month}-${year} ${istString} IST`
}
