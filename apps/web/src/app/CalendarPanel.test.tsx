import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CalendarPanel from './CalendarPanel'

const { getCalendar, createEvent } = vi.hoisted(() => ({
  getCalendar: vi.fn(),
  createEvent: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    calendar: {
      get: getCalendar,
      icsHref: (pid: string, p?: { from?: string; to?: string }) =>
        `/api/v1/projects/${pid}/calendar.ics?from=${p?.from}&to=${p?.to}`,
    },
    calendarEvents: {
      list: vi.fn(async () => []),
      create: createEvent,
      update: vi.fn(async () => ({})),
      remove: vi.fn(async () => undefined),
    },
    milestones: { update: vi.fn(async () => ({})) },
    tasks: { update: vi.fn(async () => ({})) },
    calendarSync: {
      providers: vi.fn(async () => ({ providers: [] as string[] })),
      connections: vi.fn(async () => [] as unknown[]),
      connect: vi.fn(),
      disconnect: vi.fn(),
      sync: vi.fn(),
      callbackUrl: (p: string) => `http://x/api/v1/calendar-sync/${p}/callback`,
    },
  },
}))

const ITEM = (o: Partial<Record<string, unknown>>) => ({
  end_at: null, all_day: true, status: null, phase_id: null, recurring: false, ...o,
})

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
      ITEM({ id: 'event:cal_1', source: 'event', ref_id: 'cal_1', title: 'Kickoff', start_at: '2026-08-12T10:00:00+00:00', all_day: false, status: 'confirmed' }),
      ITEM({ id: 'milestone:mil_1', source: 'milestone', ref_id: 'mil_1', title: 'Beta', start_at: '2026-08-15', status: 'planned' }),
      ITEM({ id: 'task:tsk_1', source: 'task', ref_id: 'tsk_1', title: 'Ship docs', start_at: '2026-08-20', status: 'in_progress' }),
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
    const calls = getCalendar.mock.calls
    const params = calls[calls.length - 1][1] as { from: string; to: string }
    expect(params.from <= '2026-09-01').toBe(true)
    expect(params.to >= '2026-09-30').toBe(true)
  })

  it('opens the new-event dialog with a recurrence control and creates an event', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    fireEvent.click(screen.getByRole('button', { name: '+ New event' }))
    expect(await screen.findByText('New event')).toBeTruthy()
    expect(screen.getByText('Repeats')).toBeTruthy() // recurrence field present
    fireEvent.change(screen.getByLabelText('Event title'), { target: { value: 'Design review' } })
    fireEvent.submit(screen.getByText('Save').closest('form')!)
    await waitFor(() => expect(createEvent).toHaveBeenCalled())
    const payload = createEvent.mock.calls[0][1] as { title: string; recurrence: string }
    expect(payload.title).toBe('Design review')
    expect(payload.recurrence).toBe('none')
  })

  it('filters out a source when its toggle is switched off', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('Beta')
    fireEvent.click(screen.getByRole('checkbox', { name: /Milestones/i }))
    expect(screen.queryByText('Beta')).toBeNull()
    expect(screen.getByText('Kickoff')).toBeTruthy() // other sources stay
  })

  it('switches to agenda view and lists upcoming items', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    fireEvent.click(screen.getByRole('button', { name: 'Agenda' }))
    expect(await screen.findByText(/Upcoming from/)).toBeTruthy()
    expect(screen.getByText('Kickoff')).toBeTruthy()
  })

  it('clicking a milestone routes to Planning instead of the event dialog', async () => {
    const onOpenPlanning = vi.fn()
    render(<CalendarPanel projectId="proj_1" onOpenPlanning={onOpenPlanning} />)
    await screen.findByText('Beta')
    fireEvent.click(screen.getByText('Beta'))
    expect(onOpenPlanning).toHaveBeenCalledOnce()
    expect(screen.queryByText('Edit event')).toBeNull() // no dialog for non-events
  })

  it('exposes an .ics export link for the visible range', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    const link = screen.getByText('Export .ics').closest('a')!
    expect(link.getAttribute('href')).toContain('/calendar.ics')
  })

  it('clicking anywhere on a day cell opens the create dialog', async () => {
    const { container } = render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    fireEvent.click(container.querySelector('.cal-cell')!)
    expect(await screen.findByText('New event')).toBeTruthy()
  })

  it('clicking an event chip opens the edit dialog, not create', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('Kickoff')
    fireEvent.click(screen.getByText('Kickoff'))
    expect(await screen.findByText('Edit event')).toBeTruthy()
    expect(screen.queryByText('New event')).toBeNull()
  })

  it('Sync dialog shows the not-configured message when no providers are set', async () => {
    render(<CalendarPanel projectId="proj_1" />)
    await screen.findByText('August 2026')
    fireEvent.click(screen.getByRole('button', { name: 'Sync' }))
    expect(await screen.findByText(/isn.t configured on this server/i)).toBeTruthy()
  })
})
