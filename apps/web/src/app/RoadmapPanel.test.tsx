import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import RoadmapPanel from './RoadmapPanel'

const rollup = (total: number, done: number) => ({ total, done, in_progress: 0, blocked: 0 })

vi.mock('../api/client', () => ({
  api: {
    roadmap: {
      get: vi.fn(async () => ({
        project_id: 'proj_1',
        generated_at: 't',
        phases: [
          {
            id: 'ph_1',
            title: 'Phase One',
            status: 'active',
            sort_order: 0,
            stages: [
              { id: 'st_1', title: 'Stage A', status: 'done', sort_order: 0, tasks: rollup(2, 2), pct_done: 100 },
            ],
            tasks: rollup(4, 1),
            pct_done: 25,
          },
        ],
        unphased: rollup(1, 0),
        totals: rollup(5, 1),
        pct_done: 20,
      })),
    },
  },
}))

describe('RoadmapPanel', () => {
  it('renders overall + per-phase progress with rollups', async () => {
    const onOpenPlanning = vi.fn()
    render(<RoadmapPanel projectId="proj_1" onOpenPlanning={onOpenPlanning} />)
    expect(await screen.findByText('Overall progress')).toBeTruthy()
    expect(screen.getByText('20%')).toBeTruthy()
    expect(screen.getByText('Phase One')).toBeTruthy()
    expect(screen.getByText('Stage A')).toBeTruthy()
    expect(screen.getByText('Unphased tasks')).toBeTruthy()
    expect(screen.getByText('1/4 done')).toBeTruthy()
    const bars = screen.getAllByRole('progressbar')
    expect(bars.length).toBeGreaterThanOrEqual(3)
    fireEvent.click(screen.getByRole('button', { name: 'Assign tasks' }))
    expect(onOpenPlanning).toHaveBeenCalledOnce()
  })
})
