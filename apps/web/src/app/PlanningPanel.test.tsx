import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import PlanningPanel, { nextStatusForColumn } from './PlanningPanel'

describe('nextStatusForColumn', () => {
  const review = { statuses: ['waiting', 'needs_review', 'blocked'] }
  it('returns the column primary status when the task is elsewhere', () => {
    expect(nextStatusForColumn('backlog', review)).toBe('waiting')
  })
  it('returns null (no write) when the task already fits the column', () => {
    expect(nextStatusForColumn('blocked', review)).toBeNull()
  })
})

// Stub api module so tests don't hit network
vi.mock('../api/client', () => ({
  api: {
    projects: { get: vi.fn() },
    phases: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), reorder: vi.fn() },
    stages: { list: vi.fn() },
    tasks: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), reorder: vi.fn() },
    milestones: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), reorder: vi.fn() },
    decisions: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), reorder: vi.fn() },
    risks: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), reorder: vi.fn() },
    blockers: { list: vi.fn(), create: vi.fn() },
    comments: { list: vi.fn(), create: vi.fn() },
    links: { list: vi.fn(), create: vi.fn() },
    checklistItems: { list: vi.fn(), create: vi.fn(), update: vi.fn() },
    statusOptions: { list: vi.fn(async () => []), create: vi.fn(), remove: vi.fn() },
  },
}))

import { api } from '../api/client'

type Fn = ReturnType<typeof vi.fn>
const mockApi = api as unknown as {
  projects: { get: Fn }
  phases: { list: Fn; create: Fn; update: Fn }
  stages: { list: Fn }
  tasks: { list: Fn; create: Fn; update: Fn }
  milestones: { list: Fn; create: Fn }
  decisions: { list: Fn; create: Fn }
  risks: { list: Fn; create: Fn }
  blockers: { list: Fn; create: Fn }
  comments: { list: Fn; create: Fn }
  links: { list: Fn; create: Fn }
  checklistItems: { list: Fn; create: Fn; update: Fn }
  statusOptions: { list: Fn; create: Fn; remove: Fn }
}

const PROJECT = {
  id: 'proj_1',
  workspace_id: 'ws_1',
  title: 'Test Project',
  slug: 'test-project',
  status: 'active',
  created_at: '2026-06-19T00:00:00+00:00',
  updated_at: '2026-06-19T00:00:00+00:00',
}

function setupEmpty() {
  mockApi.projects.get.mockResolvedValue(PROJECT)
  mockApi.phases.list.mockResolvedValue([])
  mockApi.stages.list.mockResolvedValue([])
  mockApi.tasks.list.mockResolvedValue([])
  mockApi.milestones.list.mockResolvedValue([])
  mockApi.decisions.list.mockResolvedValue([])
  mockApi.risks.list.mockResolvedValue([])
  mockApi.blockers.list.mockResolvedValue([])
  mockApi.comments.list.mockResolvedValue([])
  mockApi.links.list.mockResolvedValue([])
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.stages.list.mockResolvedValue([])
  mockApi.milestones.list.mockResolvedValue([])
  mockApi.comments.list.mockResolvedValue([])
  mockApi.links.list.mockResolvedValue([])
  mockApi.checklistItems.list.mockResolvedValue([])
  mockApi.statusOptions.list.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
})

describe('PlanningPanel', () => {
  it('shows loading state initially', () => {
    setupEmpty()
    render(<PlanningPanel projectId="proj_1" />)
    expect(screen.getByText('Loading…')).toBeTruthy()
  })

  it('shows project name after load', async () => {
    setupEmpty()
    render(<PlanningPanel projectId="proj_1" />)
    expect(await screen.findByText('Test Project')).toBeTruthy()
  })

  it('shows all tabs', async () => {
    setupEmpty()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    for (const name of ['Phases', 'Tasks', 'Milestones', 'Decisions', 'Risks', 'Comments', 'Links']) {
      expect(screen.getByRole('tab', { name })).toBeTruthy()
    }
  })

  it('opens on a requested tab', async () => {
    setupEmpty()
    render(<PlanningPanel projectId="proj_1" initialTab="tasks" />)
    await screen.findByText('Test Project')
    expect(screen.getByRole('tab', { name: 'Tasks' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('No tasks yet.')).toBeTruthy()
  })

  it('renders milestones with target date when present', async () => {
    setupEmpty()
    mockApi.milestones.list.mockResolvedValue([
      {
        id: 'mil_1', project_id: 'proj_1', phase_id: null, title: 'Beta launch',
        description: null, status: 'planned', target_date: '2026-08-01', sort_order: 0,
        created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
      },
    ])
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Milestones' }))
    expect(await screen.findByText('Beta launch')).toBeTruthy()
    expect(screen.getByText('2026-08-01')).toBeTruthy()
  })

  it('reads and writes against the projectId prop, not the first project', async () => {
    // Regression: the panel used to derive workspaces[0].projects[0] on its own,
    // so a second project's view could read/write the first project's data.
    mockApi.projects.get.mockResolvedValue({ ...PROJECT, id: 'proj_2', title: 'Second Project' })
    mockApi.phases.list.mockResolvedValue([])
    mockApi.tasks.list.mockResolvedValue([])
    mockApi.decisions.list.mockResolvedValue([])
    mockApi.risks.list.mockResolvedValue([])
    mockApi.blockers.list.mockResolvedValue([])
    mockApi.phases.create.mockResolvedValue({
      id: 'ph_9', project_id: 'proj_2', title: 'Kickoff', description: null,
      status: 'planned', sort_order: 1,
      created_at: '2026-06-19T00:00:00+00:00', updated_at: '2026-06-19T00:00:00+00:00',
    })

    render(<PlanningPanel projectId="proj_2" />)
    await screen.findByText('Second Project')
    expect(mockApi.projects.get).toHaveBeenCalledWith('proj_2')
    expect(mockApi.phases.list).toHaveBeenCalledWith('proj_2')
    expect(mockApi.tasks.list).toHaveBeenCalledWith('proj_2')

    fireEvent.click(screen.getByText('+ Add'))
    fireEvent.change(screen.getByPlaceholderText('Phase title'), { target: { value: 'Kickoff' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() =>
      expect(mockApi.phases.create).toHaveBeenCalledWith('proj_2', { title: 'Kickoff', status: 'planned' }),
    )
  })

  it('shows error and retry on API failure', async () => {
    mockApi.projects.get.mockRejectedValue(new Error('Network error'))
    render(<PlanningPanel projectId="proj_1" />)
    expect(await screen.findByText(/Could not load/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })

  it('shows no-phases empty state when phases list is empty', async () => {
    setupEmpty()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    expect(screen.getByText('No phases yet.')).toBeTruthy()
  })

  it('renders phases when present', async () => {
    mockApi.projects.get.mockResolvedValue(PROJECT)
    mockApi.phases.list.mockResolvedValue([
      {
        id: 'ph_1',
        project_id: 'proj_1',
        title: 'Foundation',
        description: null,
        status: 'active',
        sort_order: 1,
        created_at: '2026-06-19T00:00:00+00:00',
        updated_at: '2026-06-19T00:00:00+00:00',
      },
    ])
    mockApi.tasks.list.mockResolvedValue([])
    mockApi.decisions.list.mockResolvedValue([])
    mockApi.risks.list.mockResolvedValue([])
    mockApi.blockers.list.mockResolvedValue([])
    render(<PlanningPanel projectId="proj_1" />)
    expect(await screen.findByText('Foundation')).toBeTruthy()
    expect(screen.getByText('active')).toBeTruthy()
  })

  it('phase status dropdown shows only canonical values', async () => {
    setupEmpty()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByText('+ Add'))
    // valid canonical values present
    expect(screen.getByRole('option', { name: 'planned' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'blocked' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'canceled' })).toBeTruthy()
    // removed invalid value absent
    expect(screen.queryByRole('option', { name: 'skipped' })).toBeNull()
  })

  it('shows open blocker count badge', async () => {
    mockApi.projects.get.mockResolvedValue(PROJECT)
    mockApi.phases.list.mockResolvedValue([])
    mockApi.tasks.list.mockResolvedValue([])
    mockApi.decisions.list.mockResolvedValue([])
    mockApi.risks.list.mockResolvedValue([])
    mockApi.blockers.list.mockResolvedValue([
      {
        id: 'blk_1',
        project_id: 'proj_1',
        task_id: null,
        title: 'Infra blocked',
        description: null,
        status: 'open',
        created_at: '2026-06-19T00:00:00+00:00',
        updated_at: '2026-06-19T00:00:00+00:00',
      },
    ])
    render(<PlanningPanel projectId="proj_1" />)
    expect(await screen.findByText('1 blocked')).toBeTruthy()
  })

  it('shows a custom status as a board column and offers Add column', async () => {
    setupEmpty()
    const builtins = ['backlog', 'ready', 'in_progress', 'waiting', 'needs_review', 'blocked', 'done', 'canceled']
      .map((k, i) => ({ id: null, key: k, label: k, color: null, sort_order: i, builtin: true }))
    const custom = { id: 'sto_1', key: 'in_review', label: 'In Review', color: null, sort_order: 8, builtin: false }
    mockApi.statusOptions.list.mockResolvedValue([...builtins, custom])
    mockApi.tasks.list.mockResolvedValue([{
      id: 'tsk_1', project_id: 'proj_1', phase_id: null, stage_id: null, parent_task_id: null,
      title: 'Review PR', description: null, status: 'in_review', priority: null,
      due_at: null, sort_order: 0, created_at: 'x', updated_at: 'x',
    }])

    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    fireEvent.click(screen.getByRole('button', { name: 'Status' }))
    // The custom status renders as its own board column, and the add-column affordance is present.
    const colTitle = await screen.findByText('in review', { selector: '.ab-col-title' })
    expect(colTitle).toBeTruthy()
    expect(screen.getByRole('button', { name: '+ Add column' })).toBeTruthy()
  })

  it('shows a custom phase status as a board column', async () => {
    setupEmpty()
    const builtins = ['planned', 'active', 'blocked', 'done', 'canceled']
      .map((k, i) => ({ id: null, key: k, label: k, color: null, sort_order: i, builtin: true }))
    const custom = { id: 'sto_p', key: 'on_hold', label: 'On Hold', color: null, sort_order: 5, builtin: false }
    // Only phase requests get the custom option (task/risk stay default []).
    mockApi.statusOptions.list.mockImplementation(async (_pid: string, entity = 'task') =>
      entity === 'phase' ? [...builtins, custom] : [])
    mockApi.phases.list.mockResolvedValue([{
      id: 'ph_1', project_id: 'proj_1', title: 'Groundwork', description: null,
      status: 'on_hold', sort_order: 0, created_at: 'x', updated_at: 'x',
    }])

    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(await screen.findByText('on hold', { selector: '.ab-col-title' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '+ Add column' })).toBeTruthy()
  })

  it('updates a task phase from the expanded task controls', async () => {
    setupEmpty()
    const phase = {
      id: 'ph_1', project_id: 'proj_1', title: 'Build', description: null,
      status: 'active', sort_order: 0,
      created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
    }
    const task = {
      id: 'tsk_1', project_id: 'proj_1', phase_id: null, stage_id: null,
      title: 'Connect roadmap', description: null, status: 'backlog', priority: null,
      due_at: null, sort_order: 0,
      created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
    }
    mockApi.phases.list.mockResolvedValue([phase])
    mockApi.tasks.list.mockResolvedValue([task])
    mockApi.tasks.update.mockResolvedValue({ ...task, phase_id: phase.id })

    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))
    fireEvent.click(screen.getByRole('button', { name: 'Connect roadmap' }))
    fireEvent.change(screen.getByLabelText('Phase'), { target: { value: phase.id } })

    await waitFor(() => expect(mockApi.tasks.update).toHaveBeenCalledWith('tsk_1', {
      phase_id: 'ph_1',
      stage_id: null,
    }))
  })

  it('expands a phase to reveal its description', async () => {
    setupEmpty()
    const phase = {
      id: 'ph_1', project_id: 'proj_1', title: 'Foundation', description: 'Groundwork and scaffolding',
      status: 'planned', sort_order: 0,
      created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
    }
    mockApi.phases.list.mockResolvedValue([phase])

    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    // description is hidden until the row is expanded
    expect(screen.queryByText('Groundwork and scaffolding')).toBeNull()
    // The row's main toggle button is named exactly by its title.
    fireEvent.click(screen.getByRole('button', { name: 'Foundation' }))
    expect(screen.getByText('Groundwork and scaffolding')).toBeTruthy()
  })

  it('changes a phase status inline via the status badge popover', async () => {
    setupEmpty()
    const phase = {
      id: 'ph_1', project_id: 'proj_1', title: 'Foundation', description: null,
      status: 'planned', sort_order: 0,
      created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
    }
    mockApi.phases.list.mockResolvedValue([phase])
    mockApi.phases.update.mockResolvedValue({ ...phase, status: 'active' })

    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('button', { name: 'Change status of Foundation' }))
    fireEvent.click(screen.getByRole('option', { name: 'active' }))
    await waitFor(() => expect(mockApi.phases.update).toHaveBeenCalledWith('ph_1', { status: 'active' }))
  })
})
