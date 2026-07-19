import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TimelinePanel, { groupEventsByDay, groupEventsByEntity } from './TimelinePanel'

const ev = (id: string, at: string, entity_type = 'task') =>
  ({ id, at, event_type: 'create', entity_type, entity_id: null, actor_type: 'human', actor_id: null, actor_display: null, label: id })

vi.mock('../api/client', () => ({
  api: {
    timeline: {
      get: vi.fn(async () => ({
        project_id: 'proj_1',
        generated_at: 't',
        events: [
          {
            id: 'aud_2',
            at: '2026-07-10T12:00:00+00:00',
            event_type: 'update',
            entity_type: 'task',
            entity_id: 'tsk_1',
            actor_type: 'human',
            actor_id: 'usr_1',
            actor_display: 'Alice Smith',
            label: 'update task — Fix login bug',
          },
          {
            id: 'aud_1',
            at: '2026-07-10T11:00:00+00:00',
            event_type: 'create',
            entity_type: 'decision',
            entity_id: 'dec_1',
            actor_type: 'human',
            actor_id: null,
            actor_display: null,
            label: 'create decision — Use SQLite',
          },
        ],
      })),
    },
  },
}))

describe('TimelinePanel', () => {
  it('lists audited events newest first with actor badges', async () => {
    render(<TimelinePanel projectId="proj_1" />)
    expect(await screen.findByText('update task — Fix login bug')).toBeTruthy()
    expect(screen.getByText('create decision — Use SQLite')).toBeTruthy()
    // P16.0: a stamped actor renders as their display name; unattributed
    // events keep rendering the raw actor_type exactly as before.
    expect(screen.getByText('Alice Smith')).toBeTruthy()
    expect(screen.getAllByText('human').length).toBe(1)
  })

  it('expands an event on click to reveal its detail, and collapses again', async () => {
    render(<TimelinePanel projectId="proj_1" />)
    const row = await screen.findByRole('button', { name: /update task/i })
    // Collapsed: the entity id lives only in the detail block.
    expect(screen.queryByText('tsk_1')).toBeNull()
    fireEvent.click(row)
    expect(screen.getByText('tsk_1')).toBeTruthy()
    expect(row.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(row)
    expect(screen.queryByText('tsk_1')).toBeNull()
  })

  it('groups events into consecutive same-day buckets, order preserved', () => {
    // Local-time (no Z) midday values so day bucketing is timezone-stable.
    const groups = groupEventsByDay([
      ev('a', '2026-07-10T14:00:00'),
      ev('b', '2026-07-10T09:00:00'),
      ev('c', '2026-07-09T12:00:00'),
    ])
    expect(groups.length).toBe(2)
    expect(groups[0].events.map((e) => e.id)).toEqual(['a', 'b'])
    expect(groups[1].events.map((e) => e.id)).toEqual(['c'])
  })

  it('groups events by entity type, ordered by first appearance', () => {
    const groups = groupEventsByEntity([
      ev('a', '2026-07-10T14:00:00', 'task'),
      ev('b', '2026-07-10T09:00:00', 'phase'),
      ev('c', '2026-07-09T12:00:00', 'task'),
    ])
    expect(groups.map((g) => g.key)).toEqual(['task', 'phase'])
    expect(groups[0].events.map((e) => e.id)).toEqual(['a', 'c'])
    expect(groups[1].events.map((e) => e.id)).toEqual(['b'])
  })
})
