import { describe, it, expect, vi, beforeEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import RoadmapPanel from './RoadmapPanel'

const rollup = (total: number, done: number) => ({ total, done, in_progress: 0, blocked: 0 })

const phaseRemove = vi.fn(async () => undefined)
const phaseUpdate = vi.fn(async () => undefined)

vi.mock('../api/client', () => ({
  api: {
    phases: {
      remove: (...a: unknown[]) => phaseRemove(...(a as [])),
      update: (...a: unknown[]) => phaseUpdate(...(a as [])),
    },
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

// No RTL auto-cleanup in this suite, so each test unmounts its own render and
// queries are scoped to their container.
beforeEach(() => { cleanup(); vi.clearAllMocks() })

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

  // #97: this deleted the phase on a single menu click, with no confirmation and
  // no way back — unlike every other delete in the app.
  it('needs a second, informed click to delete a phase', async () => {
    const { container } = render(<RoadmapPanel projectId="proj_1" />)
    const view = within(container)
    fireEvent.click(await view.findByRole('button', { name: 'Actions for Phase One' }))
    // Matched by role and a label-agnostic pattern on purpose: against the
    // pre-fix code this click deletes immediately, so the assertion below is what
    // fails, rather than the test failing to find a renamed menu item.
    fireEvent.click(view.getByRole('menuitem', { name: /Delete phase/ }))

    expect(phaseRemove).not.toHaveBeenCalled()
    // The confirm states the consequence, using the counts already on screen.
    const dialog = view.getByRole('alertdialog')
    expect(dialog.textContent).toContain('1 stage is deleted')
    expect(dialog.textContent).toContain('4 tasks become unphased')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete phase' }))
    expect(phaseRemove).toHaveBeenCalledWith('ph_1')
  })

  it('cancelling leaves the phase alone', async () => {
    const { container } = render(<RoadmapPanel projectId="proj_1" />)
    const view = within(container)
    fireEvent.click(await view.findByRole('button', { name: 'Actions for Phase One' }))
    fireEvent.click(view.getByRole('menuitem', { name: /Delete phase/ }))
    fireEvent.click(within(view.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    expect(view.queryByRole('alertdialog')).toBeNull()
    expect(phaseRemove).not.toHaveBeenCalled()
  })

  // The other half of #97's silent-failure class: these calls had no .catch, so
  // a rejected delete looked exactly like a successful one.
  it('surfaces a failed delete instead of swallowing it', async () => {
    phaseRemove.mockRejectedValueOnce(new Error('409: phase is locked'))
    const { container } = render(<RoadmapPanel projectId="proj_1" />)
    const view = within(container)
    fireEvent.click(await view.findByRole('button', { name: 'Actions for Phase One' }))
    fireEvent.click(view.getByRole('menuitem', { name: /Delete phase/ }))
    fireEvent.click(within(view.getByRole('alertdialog')).getByRole('button', { name: 'Delete phase' }))
    await waitFor(() => expect(view.getByRole('alert').textContent).toContain('phase is locked'))
  })
})
