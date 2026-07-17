// Shared date helpers (native Date, no external library). Extracted from
// TimelinePanel and extended with the month-grid math the Calendar surface needs.

export const startOfDay = (d: Date): Date =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate())

/** ISO date key `YYYY-MM-DD` in LOCAL time (used to bucket items onto a day). */
export function isoDay(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** The `YYYY-MM-DD` prefix of any ISO date/datetime string (or '' if unusable). */
export function dayKeyOf(iso: string | null | undefined): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}

export function dayLabel(iso: string, now = new Date()): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const diff = Math.round((startOfDay(now).getTime() - startOfDay(d).getTime()) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

export function timeLabel(iso: string): string {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export const WEEKDAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** Add `n` months to (year, month), normalizing the month into 0–11. */
export function addMonths(year: number, month: number, n: number): { year: number; month: number } {
  const total = year * 12 + month + n
  return { year: Math.floor(total / 12), month: ((total % 12) + 12) % 12 }
}

/**
 * A 6×7 month grid (always 42 cells) of local Dates, starting on Sunday, that
 * fully contains `month` and pads leading/trailing days from the adjacent
 * months. Six rows keeps the grid a stable height across every month.
 */
export function monthMatrix(year: number, month: number): Date[][] {
  const first = new Date(year, month, 1)
  const start = new Date(year, month, 1 - first.getDay()) // back up to Sunday
  const weeks: Date[][] = []
  const cursor = new Date(start)
  for (let w = 0; w < 6; w++) {
    const row: Date[] = []
    for (let d = 0; d < 7; d++) {
      row.push(new Date(cursor))
      cursor.setDate(cursor.getDate() + 1)
    }
    weeks.push(row)
  }
  return weeks
}

/** The seven local Dates (Sun→Sat) of the week containing `d`. */
export function weekDays(d: Date): Date[] {
  const start = new Date(d.getFullYear(), d.getMonth(), d.getDate() - d.getDay())
  return Array.from({ length: 7 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i))
}

export function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}
