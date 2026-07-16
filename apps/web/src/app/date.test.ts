import { describe, it, expect } from 'vitest'
import { addMonths, dayKeyOf, isoDay, isSameDay, monthMatrix, weekDays } from './date'

describe('date helpers', () => {
  it('isoDay formats a local date as YYYY-MM-DD', () => {
    expect(isoDay(new Date(2026, 0, 5))).toBe('2026-01-05')
    expect(isoDay(new Date(2026, 11, 31))).toBe('2026-12-31')
  })

  it('dayKeyOf takes the date prefix of any ISO value', () => {
    expect(dayKeyOf('2026-08-15')).toBe('2026-08-15')
    expect(dayKeyOf('2026-08-15T09:30:00+00:00')).toBe('2026-08-15')
    expect(dayKeyOf(null)).toBe('')
  })

  it('monthMatrix returns a 6x7 grid starting on Sunday and covering the month', () => {
    // August 2026: the 1st is a Saturday.
    const grid = monthMatrix(2026, 7)
    expect(grid).toHaveLength(6)
    expect(grid.every(w => w.length === 7)).toBe(true)
    expect(grid[0][0].getDay()).toBe(0) // Sunday
    // The month's 1st appears in the first row (Saturday column).
    expect(isoDay(grid[0][6])).toBe('2026-08-01')
    // Grid fully contains the month.
    const flat = grid.flat().map(isoDay)
    expect(flat).toContain('2026-08-31')
  })

  it('addMonths normalizes across year boundaries', () => {
    expect(addMonths(2026, 11, 1)).toEqual({ year: 2027, month: 0 })
    expect(addMonths(2026, 0, -1)).toEqual({ year: 2025, month: 11 })
    expect(addMonths(2026, 5, 3)).toEqual({ year: 2026, month: 8 })
  })

  it('weekDays returns Sun..Sat for the containing week', () => {
    const wk = weekDays(new Date(2026, 7, 12)) // a Wednesday
    expect(wk).toHaveLength(7)
    expect(wk[0].getDay()).toBe(0)
    expect(wk[6].getDay()).toBe(6)
    expect(isSameDay(wk[3], new Date(2026, 7, 12))).toBe(true)
  })
})
