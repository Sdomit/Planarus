import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TimelinePanel from './TimelinePanel'

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
            label: 'update task — Fix login bug',
          },
          {
            id: 'aud_1',
            at: '2026-07-10T11:00:00+00:00',
            event_type: 'create',
            entity_type: 'decision',
            entity_id: 'dec_1',
            actor_type: 'human',
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
    expect(screen.getAllByText('human').length).toBe(2)
  })
})
