import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CalendarPanel from './CalendarPanel'

const { getCalendar, createEvent } = vi.hoisted(() => ({
  getCalendar: vi.fn(),
  createEvent: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    calendar: { get: getCalendar },
    calendarEvents: {
      create: createEvent,
      update: vi.fn(async () => ({})),
      remove: vi.fn(async () => undefined),
    },
    milestones: { update: vi.fn(async () => ({})) },
    tasks: { update: vi.fn(async () => ({})) },
  },
}))

// A fixed "today" so month headings/ranges are deterministic.
afterEach(() => { cleanup(); vi.useRealTimers() })

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date(2026, 7, 12)) // Aug 12 2026
  getCalendar.mockReset()
  createEvent.mockClear()
  getCalendar.mockResolvedValue({
    project_id: 'proj_1',
    generated_at: 't',
    items: [
      { id: 'event:cal_1', source: 'event', ref_id: 'cal_1', title: 'Kickoff', start_at: '2026-08-12T10:00:00+00:00', end_at: null, all_day: false, status: 'confirmed', phase_id: null },
      { id: 'milestone:mil_1', source: 'milestone', ref_id: 'mil_1', title: 'Beta', start_at: '2026-08-15', end_at: null, all_day: true, status: 'planned', phase_id: null },
      { id: 'task:tsk_1', source: 'task', ref_id: 'tsk_1', title: 'Ship docs', start_at: '2026-08-20', end_at: null, all_day: true, status: 'in_progress', phase_id: null },
    ],
  })
})

describe('CalendarPanel', () => {
  it('renders the month heading and items from all three sources', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    expect(await screen.findByText('August 2026')).toBeTruthy()
    expect(screen.getByText('Kickoff')).toBeTruthy()
    expect(screen.getByText('Beta')).toBeTruthy()
    expect(screen.getByText('Ship docs')).toBeTruthy()
  })

  it('fetches the visible range when navigating months', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    fireEvent.click(screen.getByLabelText('Next'))
    expect(await screen.findByText('September 2026')).toBeTruthy()
    // The most recent fetch requested a September-spanning range.
    const calls = getCalendar.mock.calls
    const params = calls[calls.length - 1][1] as { from: string; to: string }
    expect(params.from <= '2026-09-01').toBe(true)
    expect(params.to >= '2026-09-30').toBe(true)
  })

  it('opens the new-event dialog and creates an event', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    fireEvent.click(screen.getByRole('button', { name: '+ New event' }))
    expect(await screen.findByText('New event')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Event title'), { target: { value: 'Design review' } })
    fireEvent.submit(screen.getByText('Save').closest('form')!)
    await waitFor(() => expect(createEvent).toHaveBeenCalled())
    const payload = createEvent.mock.calls[0][1] as { title: string }
    expect(payload.title).toBe('Design review')
  })
})
