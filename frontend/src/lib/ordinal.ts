/**
 * Returns the English ordinal string for a non-negative integer.
 *   ordinal(1)   → "1st"
 *   ordinal(2)   → "2nd"
 *   ordinal(3)   → "3rd"
 *   ordinal(4)   → "4th"
 *   ordinal(11)  → "11th"
 *   ordinal(12)  → "12th"
 *   ordinal(13)  → "13th"
 *   ordinal(21)  → "21st"
 *   ordinal(52)  → "52nd"
 *   ordinal(53)  → "53rd"
 *   ordinal(100) → "100th"
 *   ordinal(101) → "101st"
 *   ordinal(111) → "111th"
 *   ordinal(112) → "112th"
 *   ordinal(113) → "113th"
 *
 * Special-cases 11, 12, 13 (and 111–113, 211–213, …) as "th" regardless of
 * the last digit. All other numbers follow the last-digit rule.
 */
export function ordinal(n: number): string {
  const abs = Math.abs(Math.floor(n))
  const lastTwo = abs % 100
  // 11th, 12th, 13th — and their multiples (111th, 112th, …)
  if (lastTwo >= 11 && lastTwo <= 13) return `${abs}th`
  const lastOne = abs % 10
  if (lastOne === 1) return `${abs}st`
  if (lastOne === 2) return `${abs}nd`
  if (lastOne === 3) return `${abs}rd`
  return `${abs}th`
}
