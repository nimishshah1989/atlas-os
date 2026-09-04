// src/lib/format.ts — pure formatters shared by every surface.
// The board is a US-market instrument, so times render in New York (ET) unless a caller says
// otherwise. Money and percentages arrive as postgres NUMERIC strings and are formatted as
// strings: no float arithmetic touches a monetary value (rule #5).

export const BOARD_TZ = 'America/New_York'

const TZ_LABEL: Record<string, string> = {
  'America/New_York': 'ET',
  'Asia/Kolkata': 'IST',
  UTC: 'UTC',
}
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

type Zoned = { year: number; month: number; day: number; hour: number; minute: number }

// Intl does the zone conversion only; names come from the tables above so output never depends
// on ICU's locale data (en-GB, for one, abbreviates September as "Sept").
function zoned(d: Date, tz: string): Zoned {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(d)
  const num = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((p) => p.type === type)?.value)
  return { year: num('year'), month: num('month'), day: num('day'), hour: num('hour'), minute: num('minute') }
}

const pad2 = (n: number) => String(n).padStart(2, '0')
const weekdayOf = ({ year, month, day }: Zoned) =>
  WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]

/** The as-of stamp on every surface: "Thu 3 Sep 2026, 21:00 ET". */
export function formatAsOf(d: Date, tz: string = BOARD_TZ): string {
  const z = zoned(d, tz)
  return `${weekdayOf(z)} ${z.day} ${MONTHS[z.month - 1]} ${z.year}, ${pad2(z.hour)}:${pad2(z.minute)} ${TZ_LABEL[tz] ?? tz}`
}

/** A compact table timestamp: "3 Sep 21:00" (zone named in the column header). */
export function formatShortDateTime(d: Date, tz: string = BOARD_TZ): string {
  const z = zoned(d, tz)
  return `${z.day} ${MONTHS[z.month - 1]} ${pad2(z.hour)}:${pad2(z.minute)}`
}

/** A postgres `date` selected as text ("2026-09-03") → "3 Sep 2026". No zone shift is possible. */
export function formatIsoDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) throw new TypeError(`Not an ISO date: ${JSON.stringify(iso)}`)
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`
}

// ── decimal strings ─────────────────────────────────────────────────────────

const DECIMAL_RE = /^-?\d+(\.\d+)?$/

type Rounded = { negative: boolean; zero: boolean; int: string; frac: string }

// Half-up rounding on the digit string with BigInt — a NUMERIC never passes through a double.
function roundDecimal(s: string, decimals: number): Rounded {
  if (!DECIMAL_RE.test(s)) throw new TypeError(`Not a decimal string: ${JSON.stringify(s)}`)
  const negative = s.startsWith('-')
  const [i, f = ''] = (negative ? s.slice(1) : s).split('.')
  const digits = f.padEnd(decimals + 1, '0').slice(0, decimals + 1)
  const scaled = (BigInt(i + digits) + 5n) / 10n
  const str = scaled.toString().padStart(decimals + 1, '0')
  const int = str.slice(0, str.length - decimals)
  const frac = decimals > 0 ? str.slice(str.length - decimals) : ''
  const zero = /^0*$/.test(int + frac)
  return { negative: negative && !zero, zero, int, frac }
}

const group = (int: string) => int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

// ×100 by moving the decimal point, so a fraction becomes a percentage without arithmetic.
function timesHundred(s: string): string {
  if (!DECIMAL_RE.test(s)) throw new TypeError(`Not a decimal string: ${JSON.stringify(s)}`)
  const negative = s.startsWith('-')
  const [i, f = ''] = (negative ? s.slice(1) : s).split('.')
  const frac = f.padEnd(2, '0')
  const int = (i + frac.slice(0, 2)).replace(/^0+(?=\d)/, '')
  const rest = frac.slice(2)
  return `${negative ? '-' : ''}${int}${rest ? '.' + rest : ''}`
}

function numberToDecimal(n: number): string {
  if (!Number.isFinite(n)) throw new TypeError(`Not a finite number: ${n}`)
  const s = String(n)
  return s.includes('e') ? n.toFixed(20).replace(/0+$/, '').replace(/\.$/, '') : s
}

/** A NUMERIC string in USD: "1234.5" → "$1,234.50". Null renders as an em dash. */
export function formatUsd(value: string | null | undefined, decimals = 2): string {
  if (value == null || value === '') return '—'
  const { negative, int, frac } = roundDecimal(value, decimals)
  return `${negative ? '-' : ''}$${group(int)}${frac ? '.' + frac : ''}`
}

/** A FRACTION (0.1234, as a NUMERIC string or a number) → "12.3%". `sign` prefixes "+" to gains. */
export function formatPct(
  fraction: string | number | null | undefined,
  decimals = 1,
  opts: { sign?: boolean } = {},
): string {
  if (fraction == null || fraction === '') return '—'
  const s = typeof fraction === 'number' ? numberToDecimal(fraction) : fraction
  const { negative, zero, int, frac } = roundDecimal(timesHundred(s), decimals)
  const sign = negative ? '-' : opts.sign && !zero ? '+' : ''
  return `${sign}${group(int)}${frac ? '.' + frac : ''}%`
}

// ── plain numbers (counts, scores, statistics — never money) ───────────────

export function formatNum(n: number | null | undefined, decimals = 0): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m < 60 ? `${m}m ${s}s` : `${Math.floor(m / 60)}h ${m % 60}m`
}

/** "3 hours ago" / "2 days ago" — for the stale-in-words copy. */
export function formatAge(hours: number): string {
  if (hours < 1) return 'under an hour ago'
  if (hours < 48) {
    const h = Math.round(hours)
    return `${h} hour${h === 1 ? '' : 's'} ago`
  }
  const d = Math.round(hours / 24)
  return `${d} days ago`
}
