import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import PlanningPanel, { nextStatusForColumn, phaseRollups } from './PlanningPanel'

// #88: built-ins report their own category; only `done`/`canceled` are special.
const STATUS_CATEGORY = (key: string) =>
  key === 'done' ? 'done' as const : key === 'canceled' ? 'canceled' as const : 'open' as const

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
    comments: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
    links: { list: vi.fn(), create: vi.fn() },
    checklistItems: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
    statusOptions: { list: vi.fn(async () => []), create: vi.fn(), update: vi.fn(), reorder: vi.fn(), remove: vi.fn() },
    members: { list: vi.fn(async () => []) },
  },
}))

import { api } from '../api/client'

type Fn = ReturnType<typeof vi.fn>
const mockApi = api as unknown as {
  projects: { get: Fn }
  phases: { list: Fn; create: Fn; update: Fn }
  stages: { list: Fn }
  tasks: { list: Fn; create: Fn; update: Fn; reorder: Fn }
  milestones: { list: Fn; create: Fn }
  decisions: { list: Fn; create: Fn; update: Fn }
  risks: { list: Fn; create: Fn; update: Fn }
  blockers: { list: Fn; create: Fn }
  comments: { list: Fn; create: Fn; update: Fn; remove: Fn }
  links: { list: Fn; create: Fn }
  checklistItems: { list: Fn; create: Fn; update: Fn; remove: Fn }
  statusOptions: { list: Fn; create: Fn; update: Fn; reorder: Fn; remove: Fn }
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

  it('shows the assignee name on an assigned task (P16.3)', async () => {
    setupEmpty()
    mockApi.tasks.list.mockResolvedValue([
      {
        id: 'tsk_1', project_id: 'proj_1', phase_id: null, stage_id: null, parent_task_id: null,
        title: 'Wire the API', description: null, status: 'backlog', priority: null,
        due_at: null, sort_order: 0, assignee_id: 'usr_2', assignee_display: 'Sam Rivera',
        created_at: '2026-07-19T00:00:00+00:00', updated_at: '2026-07-19T00:00:00+00:00',
      },
    ])
    render(<PlanningPanel projectId="proj_1" initialTab="tasks" />)
    expect(await screen.findByText('Wire the API')).toBeTruthy()
    // The row carries the assignee chip (server-resolved display name).
    expect(screen.getByText('Sam Rivera')).toBeTruthy()
  })

  it('sets a due date on create and flags an overdue task (#90)', async () => {
    setupEmpty()
    mockApi.tasks.list.mockResolvedValue([
      {
        id: 'tsk_due', project_id: 'proj_1', phase_id: null, stage_id: null, parent_task_id: null,
        title: 'Ship the beta', description: null, status: 'in_progress', priority: null,
        due_at: '2020-01-02', sort_order: 0, assignee_id: null, assignee_display: null,
        created_at: '2026-07-19T00:00:00+00:00', updated_at: '2026-07-19T00:00:00+00:00',
      },
    ])
    mockApi.tasks.create.mockResolvedValue({
      id: 'tsk_new', project_id: 'proj_1', phase_id: null, stage_id: null, parent_task_id: null,
      title: 'Follow up', description: null, status: 'backlog', priority: null,
      due_at: '2026-09-01', sort_order: 1, assignee_id: null, assignee_display: null,
      created_at: '2026-07-19T00:00:00+00:00', updated_at: '2026-07-19T00:00:00+00:00',
    })
    render(<PlanningPanel projectId="proj_1" initialTab="tasks" />)
    await screen.findByText('Ship the beta')
    expect(screen.getByText(/Overdue 2020-01-02/)).toBeTruthy()

    // The inlet the audit found missing: a date the human can actually type into.
    fireEvent.click(screen.getByText('+ Add'))
    fireEvent.change(screen.getByLabelText('Task title'), { target: { value: 'Follow up' } })
    fireEvent.change(screen.getByLabelText('Task due date'), { target: { value: '2026-09-01' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() =>
      expect(mockApi.tasks.create).toHaveBeenCalledWith(
        'proj_1',
        expect.objectContaining({ title: 'Follow up', due_at: '2026-09-01' }),
      ),
    )
  })

  it('shows the comment author display when present (P16.3)', async () => {
    setupEmpty()
    mockApi.comments.list.mockResolvedValue([
      {
        id: 'cmt_1', project_id: 'proj_1', entity_type: 'project', entity_id: 'proj_1',
        body: 'looks good', author_type: 'human', author_id: 'usr_2', author_display: 'Sam Rivera',
        status: 'active', created_at: '2026-07-19T00:00:00+00:00', updated_at: null,
      },
    ])
    render(<PlanningPanel projectId="proj_1" initialTab="comments" />)
    await screen.findByText('Test Project')
    expect(await screen.findByText(/Sam Rivera/)).toBeTruthy()
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
      .map((k, i) => ({ id: null, key: k, label: k, category: STATUS_CATEGORY(k), color: null, sort_order: i, builtin: true }))
    const custom = { id: 'sto_1', key: 'in_review', label: 'In Review', category: 'open' as const, color: null, sort_order: 8, builtin: false }
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
      .map((k, i) => ({ id: null, key: k, label: k, category: STATUS_CATEGORY(k), color: null, sort_order: i, builtin: true }))
    const custom = { id: 'sto_p', key: 'on_hold', label: 'On Hold', category: 'open' as const, color: null, sort_order: 5, builtin: false }
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

  it('removes a checklist item from the expanded task', async () => {
    setupEmpty()
    const task = {
      id: 'tsk_1', project_id: 'proj_1', phase_id: null, stage_id: null,
      title: 'Ship it', description: null, status: 'backlog', priority: null,
      due_at: null, sort_order: 0,
      created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
    }
    const item = {
      id: 'cli_1', task_id: 'tsk_1', label: 'Write docs', done: false, sort_order: 0,
      created_at: '2026-07-13T00:00:00+00:00', updated_at: '2026-07-13T00:00:00+00:00',
    }
    mockApi.tasks.list.mockResolvedValue([task])
    mockApi.checklistItems.list.mockResolvedValue([item])
    mockApi.checklistItems.remove.mockResolvedValue(undefined)

    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ship it' }))
    expect(await screen.findByText('Write docs')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Remove Write docs' }))
    await waitFor(() => expect(mockApi.checklistItems.remove).toHaveBeenCalledWith('cli_1'))
    await waitFor(() => expect(screen.queryByText('Write docs')).toBeNull())
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

describe('StatusManager (manage statuses)', () => {
  const BUILTINS = ['backlog', 'ready', 'in_progress', 'waiting', 'needs_review', 'blocked', 'done', 'canceled']
    .map((k, i) => ({ id: null, key: k, label: k, category: STATUS_CATEGORY(k), color: null, sort_order: i, builtin: true }))
  const CUSTOM_A = { id: 'sto_a', key: 'in_review', label: 'In Review', category: 'open' as const, color: '#8b5cf6', sort_order: 8, builtin: false }
  const CUSTOM_B = { id: 'sto_b', key: 'on_hold', label: 'On Hold', category: 'open' as const, color: null, sort_order: 9, builtin: false }

  async function openTaskManager() {
    setupEmpty()
    mockApi.statusOptions.list.mockImplementation(async (_pid: string, entity = 'task') =>
      entity === 'task' ? [...BUILTINS, CUSTOM_A, CUSTOM_B] : [])
    render(<PlanningPanel projectId="proj_1" initialTab="tasks" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('button', { name: 'Manage statuses' }))
    return await screen.findByRole('dialog')
  }

  it('lists built-in and custom statuses', async () => {
    const dialog = await openTaskManager()
    expect(within(dialog).getByLabelText('Rename In Review')).toBeTruthy()
    expect(within(dialog).getByLabelText('Rename On Hold')).toBeTruthy()
    expect(within(dialog).getAllByText('built-in').length).toBe(BUILTINS.length)
  })

  it('renames a custom status (keeping its key)', async () => {
    const dialog = await openTaskManager()
    const input = within(dialog).getByLabelText('Rename In Review')
    fireEvent.change(input, { target: { value: 'Under Review' } })
    fireEvent.blur(input)
    await waitFor(() =>
      expect(mockApi.statusOptions.update).toHaveBeenCalledWith('sto_a', { label: 'Under Review' }))
  })

  it('recolors a custom status', async () => {
    const dialog = await openTaskManager()
    fireEvent.change(within(dialog).getByLabelText('Color for On Hold'), { target: { value: '#22c55e' } })
    await waitFor(() =>
      expect(mockApi.statusOptions.update).toHaveBeenCalledWith('sto_b', { color: '#22c55e' }))
  })

  it('reorders custom statuses with the up control', async () => {
    const dialog = await openTaskManager()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move On Hold up' }))
    await waitFor(() =>
      expect(mockApi.statusOptions.reorder).toHaveBeenCalledWith('proj_1', 'task', ['sto_b', 'sto_a']))
  })

  it('deletes a custom status', async () => {
    const dialog = await openTaskManager()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete In Review' }))
    await waitFor(() => expect(mockApi.statusOptions.remove).toHaveBeenCalledWith('sto_a'))
  })

  it('adds a new status from the manager', async () => {
    const dialog = await openTaskManager()
    fireEvent.change(within(dialog).getByLabelText('New status name'), { target: { value: 'Verifying' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(mockApi.statusOptions.create).toHaveBeenCalledWith(
      'proj_1', expect.objectContaining({ entity_type: 'task', label: 'Verifying' })))
  })

  // #88: a column's meaning drives the roadmap %, the reminders and the agent
  // brief, so it has to be settable from the same dialog that creates it.
  it('marks a custom status as done', async () => {
    const dialog = await openTaskManager()
    fireEvent.change(within(dialog).getByLabelText('Meaning of In Review'), { target: { value: 'done' } })
    await waitFor(() =>
      expect(mockApi.statusOptions.update).toHaveBeenCalledWith('sto_a', { category: 'done' }))
  })

  it('adds a new status with a chosen meaning', async () => {
    const dialog = await openTaskManager()
    fireEvent.change(within(dialog).getByLabelText('New status name'), { target: { value: 'Shipped' } })
    fireEvent.change(within(dialog).getByLabelText('New status meaning'), { target: { value: 'done' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(mockApi.statusOptions.create).toHaveBeenCalledWith(
      'proj_1', expect.objectContaining({ label: 'Shipped', category: 'done' })))
  })

  it('surfaces a delete-in-use error without crashing', async () => {
    const dialog = await openTaskManager()
    mockApi.statusOptions.remove.mockRejectedValueOnce(new Error('cannot delete a status that is still in use'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete On Hold' }))
    expect(await within(dialog).findByRole('alert')).toBeTruthy()
    expect(within(dialog).getByText(/still in use/)).toBeTruthy()
  })
})

// --- Phase 19 (D45): the phase spine in the UI -------------------------------

describe('phaseRollups', () => {
  const phased = (over: Record<string, unknown> = {}) => ({ phase_id: 'pha_1', status: 'open', ...over })

  it('counts done/total tasks, decisions and only OPEN risks per phase', () => {
    const rollups = phaseRollups(
      [
        phased({ status: 'done' }), phased({ status: 'done' }), phased({ status: 'in_progress' }),
        { phase_id: null, status: 'done' },            // unphased: excluded
      ] as never,
      [phased(), phased(), { phase_id: null }] as never,
      [
        phased({ status: 'open' }),
        phased({ status: 'monitoring' }),
        phased({ status: 'mitigated' }),               // closed: excluded
        phased({ status: 'accepted' }),                // closed: excluded
      ] as never,
    )
    expect(rollups.get('pha_1')).toEqual({
      tasksDone: 2, tasksTotal: 3, decisions: 2, openRisks: 2,
    })
  })

  it('leaves a phase with nothing attached out of the map entirely', () => {
    expect(phaseRollups([], [], []).get('pha_1')).toBeUndefined()
  })
})

describe('phase spine UI', () => {
  const PHASE = {
    id: 'pha_1', project_id: 'proj_1', title: 'Auth phase', description: null,
    status: 'active', sort_order: 0, created_at: 'x', updated_at: 'x',
  }
  const DECISION = {
    id: 'dec_1', project_id: 'proj_1', phase_id: 'pha_1', title: 'Use OAuth',
    decision: 'OAuth 2.1', context: null, status: 'accepted', sort_order: 0,
    created_at: 'x', updated_at: 'x',
  }
  const RISK = {
    id: 'rsk_1', project_id: 'proj_1', phase_id: 'pha_1', title: 'Token leak',
    description: null, severity: 'high', status: 'open', mitigation: null,
    sort_order: 0, created_at: 'x', updated_at: 'x',
  }

  function setupPhased() {
    setupEmpty()
    mockApi.phases.list.mockResolvedValue([PHASE])
    mockApi.decisions.list.mockResolvedValue([DECISION])
    mockApi.risks.list.mockResolvedValue([RISK])
  }

  it('shows the roll-up on the phase row', async () => {
    setupPhased()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    // Phase 22.1 split the roll-up into one button per count, so the summary is
    // no longer a single text node — assert the parts.
    expect(await screen.findByRole('button', { name: '1 decision' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '1 open risk' })).toBeTruthy()
  })

  it('shows the phase chip on a decision and lets it be re-assigned', async () => {
    setupPhased()
    mockApi.decisions.update.mockResolvedValue({ ...DECISION, phase_id: null })
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Decisions' }))

    expect(await screen.findByText('Auth phase')).toBeTruthy()   // chip
    fireEvent.click(screen.getByRole('button', { name: 'Use OAuth' }))
    const picker = await screen.findByLabelText('Phase for Use OAuth')
    fireEvent.change(picker, { target: { value: '' } })
    // Clearing sends null, not undefined — otherwise the field is omitted and
    // the PATCH silently keeps the old phase.
    await waitFor(() => expect(mockApi.decisions.update).toHaveBeenCalledWith('dec_1', { phase_id: null }))
  })

  it('shows the phase chip on a risk', async () => {
    setupPhased()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Risks' }))
    expect(await screen.findByText('Auth phase')).toBeTruthy()
  })
})

// --- #86: filtered phase drill-down must not corrupt the list ---------------

describe('reorder in a phase drill-down (#86)', () => {
  const PHASE = {
    id: 'pha_1', project_id: 'proj_1', title: 'Auth phase', description: null,
    status: 'active', sort_order: 0, created_at: 'x', updated_at: 'x',
  }
  const task = (id: string, title: string, sort_order: number) => ({
    id, project_id: 'proj_1', phase_id: 'pha_1', stage_id: null, parent_task_id: null,
    title, description: null, status: 'backlog', priority: null,
    due_at: null, sort_order, assignee_id: null, assignee_display: null,
    created_at: 'x', updated_at: 'x',
  })

  function setupTwoPhasedTasks() {
    setupEmpty()
    mockApi.phases.list.mockResolvedValue([PHASE])
    mockApi.tasks.list.mockResolvedValue([task('tsk_a', 'Alpha task', 0), task('tsk_b', 'Beta task', 1)])
  }

  it('shows the move controls in the unfiltered task list', async () => {
    setupTwoPhasedTasks()
    render(<PlanningPanel projectId="proj_1" initialTab="tasks" />)
    expect(await screen.findByText('Beta task')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Move Beta task up' })).toBeTruthy()
  })

  it('hides the move controls after drilling into a phase, so a filtered reorder cannot corrupt the list', async () => {
    setupTwoPhasedTasks()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    // Drill into the phase's tasks via its roll-up chip (sets the phase filter).
    fireEvent.click(await screen.findByRole('button', { name: '0/2 tasks' }))
    // Both in-phase tasks are shown...
    expect(await screen.findByText('Beta task')).toBeTruthy()
    expect(screen.getByText('Alpha task')).toBeTruthy()
    // ...but reorder is disabled while filtered: no move buttons, so
    // useListReorder can never persist a filtered subset. (#86)
    expect(screen.queryByRole('button', { name: 'Move Beta task up' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Move Alpha task up' })).toBeNull()
    expect(mockApi.tasks.reorder).not.toHaveBeenCalled()
  })
})

// --- Phase 22 (D56): attachments on any entity ------------------------------

describe('entity attachments', () => {
  const PHASE = {
    id: 'pha_1', project_id: 'proj_1', title: 'Auth phase', description: null,
    status: 'active', sort_order: 0, created_at: 'x', updated_at: 'x',
  }
  const DECISION = {
    id: 'dec_1', project_id: 'proj_1', phase_id: null, title: 'Use OAuth',
    decision: 'OAuth 2.1', context: null, status: 'accepted', sort_order: 0,
    created_at: 'x', updated_at: 'x',
  }
  const note = (id: string, entity_type: string, entity_id: string, body: string) => ({
    id, project_id: 'proj_1', entity_type, entity_id, body,
    author_type: 'human', author_id: null, author_display: null,
    status: 'active', created_at: '2026-07-21T00:00:00+00:00', updated_at: null,
  })
  const link = (id: string, entity_type: string, entity_id: string, title: string) => ({
    id, project_id: 'proj_1', entity_type, entity_id,
    url: `https://example.com/${id}`, title, created_at: 'x',
  })

  function setupAttachments() {
    setupEmpty()
    mockApi.phases.list.mockResolvedValue([PHASE])
    mockApi.decisions.list.mockResolvedValue([DECISION])
    mockApi.comments.list.mockResolvedValue([
      note('cmt_p', 'phase', 'pha_1', 'note on the phase'),
      note('cmt_d', 'decision', 'dec_1', 'note on the decision'),
      note('cmt_other', 'task', 'tsk_9', 'note on someone else'),
    ])
    mockApi.links.list.mockResolvedValue([
      link('lnk_d', 'decision', 'dec_1', 'RFC 9700'),
      link('lnk_other', 'task', 'tsk_9', 'unrelated link'),
    ])
  }

  it('shows only the notes and links belonging to the expanded entity', async () => {
    setupAttachments()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Decisions' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use OAuth' }))

    expect(await screen.findByText('note on the decision')).toBeTruthy()
    expect(screen.getByText('RFC 9700')).toBeTruthy()
    // Attachments on other entities must not leak into this row.
    expect(screen.queryByText('note on someone else')).toBeNull()
    expect(screen.queryByText('unrelated link')).toBeNull()
    expect(screen.queryByText('note on the phase')).toBeNull()
  })

  it('adds a note to a phase with the right entity_type and entity_id', async () => {
    setupAttachments()
    mockApi.comments.create.mockResolvedValue(note('cmt_new', 'phase', 'pha_1', 'fresh'))
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(await screen.findByRole('button', { name: 'Auth phase' }))

    const box = await screen.findByLabelText('Add a note on Auth phase')
    fireEvent.change(box, { target: { value: 'fresh' } })
    fireEvent.click(screen.getByRole('button', { name: 'Note' }))

    await waitFor(() => expect(mockApi.comments.create).toHaveBeenCalledWith('proj_1', {
      entity_type: 'phase', entity_id: 'pha_1', body: 'fresh',
    }))
  })

  it('adds a link to a decision, and never refetches to do it', async () => {
    setupAttachments()
    mockApi.links.create.mockResolvedValue(link('lnk_new', 'decision', 'dec_1', 'Spec'))
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(screen.getByRole('tab', { name: 'Decisions' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use OAuth' }))

    const listCallsBefore = mockApi.links.list.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: 'Link' }))
    fireEvent.change(await screen.findByLabelText('Link URL for Use OAuth'), {
      target: { value: 'https://example.com/spec' },
    })
    fireEvent.change(screen.getByLabelText('Link title for Use OAuth'), { target: { value: 'Spec' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save link' }))

    await waitFor(() => expect(mockApi.links.create).toHaveBeenCalledWith('proj_1', {
      entity_type: 'decision', entity_id: 'dec_1', url: 'https://example.com/spec', title: 'Spec',
    }))
    // The whole point of reading from shared state: no per-row list call.
    expect(mockApi.links.list.mock.calls.length).toBe(listCallsBefore)
  })
})

// --- Phase 22.1: the phase as a workspace -----------------------------------

describe('phase workspace', () => {
  const PHASE = {
    id: 'pha_1', project_id: 'proj_1', title: 'Build', description: null,
    status: 'active', sort_order: 0, created_at: 'x', updated_at: 'x',
  }
  const mkRisk = (id: string, title: string, phase_id: string | null) => ({
    id, project_id: 'proj_1', phase_id, title, description: null,
    severity: 'high', status: 'open', mitigation: null, sort_order: 0,
    created_at: 'x', updated_at: 'x',
  })

  function setupWorkspace() {
    setupEmpty()
    mockApi.phases.list.mockResolvedValue([PHASE])
    mockApi.risks.list.mockResolvedValue([
      mkRisk('rsk_in', 'inside the phase', 'pha_1'),
      mkRisk('rsk_out', 'project wide', null),
    ])
  }

  it('clicking a roll-up count opens that tab narrowed to the phase', async () => {
    setupWorkspace()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')

    fireEvent.click(await screen.findByRole('button', { name: '1 open risk' }))

    expect(await screen.findByText('inside the phase')).toBeTruthy()
    // The unphased risk is not in this phase, so it drops out of the view.
    expect(screen.queryByText('project wide')).toBeNull()
    expect(screen.getByRole('tab', { name: 'Risks' }).getAttribute('aria-selected')).toBe('true')
  })

  it('the filter is visible and clearable, never a silent narrowing', async () => {
    setupWorkspace()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(await screen.findByRole('button', { name: '1 open risk' }))
    await screen.findByText('inside the phase')

    expect(screen.getByText(/Showing/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }))

    expect(await screen.findByText('project wide')).toBeTruthy()
    expect(screen.queryByText(/Showing/)).toBeNull()
  })


  it('filters blockers by the phase of their task, not just risks', async () => {
    // Blockers have no phase_id — they reach a phase through their task. A
    // browser check caught them ignoring the filter while the chip claimed
    // "Showing <phase> only".
    setupWorkspace()
    mockApi.tasks.list.mockResolvedValue([
      { id: 'tsk_in', project_id: 'proj_1', phase_id: 'pha_1', stage_id: null, parent_task_id: null,
        title: 'in phase', description: null, status: 'backlog', priority: null, due_at: null,
        sort_order: 0, assignee_id: null, assignee_display: null, created_at: 'x', updated_at: 'x' },
    ])
    mockApi.blockers.list.mockResolvedValue([
      { id: 'blk_in', project_id: 'proj_1', task_id: 'tsk_in', title: 'blocker in phase',
        description: null, status: 'open', created_at: 'x', updated_at: 'x' },
      { id: 'blk_out', project_id: 'proj_1', task_id: null, title: 'blocker project wide',
        description: null, status: 'open', created_at: 'x', updated_at: 'x' },
    ])
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(await screen.findByRole('button', { name: '1 open risk' }))

    expect(await screen.findByText('blocker in phase')).toBeTruthy()
    expect(screen.queryByText('blocker project wide')).toBeNull()
  })

  it('"add risk here" opens the create form already scoped to the phase', async () => {
    setupWorkspace()
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(await screen.findByRole('button', { name: 'Build' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add risk here' }))

    const select = await screen.findByLabelText('Risk phase') as HTMLSelectElement
    expect(select.value).toBe('pha_1')
  })

  it('creates a milestone with its phase — the form used to drop it', async () => {
    setupWorkspace()
    mockApi.milestones.create.mockResolvedValue({
      id: 'mil_1', project_id: 'proj_1', phase_id: 'pha_1', title: 'Beta',
      description: null, status: 'planned', target_date: null, sort_order: 0,
      created_at: 'x', updated_at: 'x',
    })
    render(<PlanningPanel projectId="proj_1" />)
    await screen.findByText('Test Project')
    fireEvent.click(await screen.findByRole('button', { name: 'Build' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add milestone here' }))

    fireEvent.change(await screen.findByLabelText('Milestone title'), { target: { value: 'Beta' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockApi.milestones.create).toHaveBeenCalledWith('proj_1',
      expect.objectContaining({ title: 'Beta', phase_id: 'pha_1' })))
  })
})
