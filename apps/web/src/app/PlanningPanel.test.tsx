import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import PlanningPanel from './PlanningPanel'

// Stub api module so tests don't hit network
vi.mock('../api/client', () => ({
  api: {
    workspaces: { list: vi.fn() },
    projects: { list: vi.fn() },
    phases: { list: vi.fn(), create: vi.fn() },
    tasks: { list: vi.fn(), create: vi.fn() },
    decisions: { list: vi.fn(), create: vi.fn() },
    risks: { list: vi.fn(), create: vi.fn() },
    blockers: { list: vi.fn(), create: vi.fn() },
  },
}))

import { api } from '../api/client'

const mockApi = api as unknown as {
  workspaces: { list: ReturnType<typeof vi.fn> }
  projects: { list: ReturnType<typeof vi.fn> }
  phases: { list: ReturnType<typeof vi.fn>; create: ReturnType<typeof vi.fn> }
  tasks: { list: ReturnType<typeof vi.fn>; create: ReturnType<typeof vi.fn> }
  decisions: { list: ReturnType<typeof vi.fn>; create: ReturnType<typeof vi.fn> }
  risks: { list: ReturnType<typeof vi.fn>; create: ReturnType<typeof vi.fn> }
  blockers: { list: ReturnType<typeof vi.fn>; create: ReturnType<typeof vi.fn> }
}

const WORKSPACE = { id: 'ws_1', name: 'Test WS', slug: 'test-ws' }
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
  mockApi.workspaces.list.mockResolvedValue([WORKSPACE])
  mockApi.projects.list.mockResolvedValue([PROJECT])
  mockApi.phases.list.mockResolvedValue([])
  mockApi.tasks.list.mockResolvedValue([])
  mockApi.decisions.list.mockResolvedValue([])
  mockApi.risks.list.mockResolvedValue([])
  mockApi.blockers.list.mockResolvedValue([])
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('PlanningPanel', () => {
  it('shows loading state initially', () => {
    setupEmpty()
    render(<PlanningPanel />)
    expect(screen.getByText('Loading…')).toBeTruthy()
  })

  it('shows project name after load', async () => {
    setupEmpty()
    render(<PlanningPanel />)
    expect(await screen.findByText('Test Project')).toBeTruthy()
  })

  it('shows all four tabs', async () => {
    setupEmpty()
    render(<PlanningPanel />)
    await screen.findByText('Test Project')
    expect(screen.getByRole('tab', { name: 'Phases' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Tasks' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Decisions' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Risks' })).toBeTruthy()
  })

  it('shows no-project message when workspace is empty', async () => {
    mockApi.workspaces.list.mockResolvedValue([WORKSPACE])
    mockApi.projects.list.mockResolvedValue([])
    render(<PlanningPanel />)
    expect(await screen.findByText(/No project yet/)).toBeTruthy()
  })

  it('shows error and retry on API failure', async () => {
    mockApi.workspaces.list.mockRejectedValue(new Error('Network error'))
    render(<PlanningPanel />)
    expect(await screen.findByText(/Could not load/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })

  it('shows no-phases empty state when phases list is empty', async () => {
    setupEmpty()
    render(<PlanningPanel />)
    await screen.findByText('Test Project')
    expect(screen.getByText('No phases yet.')).toBeTruthy()
  })

  it('renders phases when present', async () => {
    mockApi.workspaces.list.mockResolvedValue([WORKSPACE])
    mockApi.projects.list.mockResolvedValue([PROJECT])
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
    render(<PlanningPanel />)
    expect(await screen.findByText('Foundation')).toBeTruthy()
    expect(screen.getByText('active')).toBeTruthy()
  })

  it('phase status dropdown shows only canonical values', async () => {
    setupEmpty()
    render(<PlanningPanel />)
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
    mockApi.workspaces.list.mockResolvedValue([WORKSPACE])
    mockApi.projects.list.mockResolvedValue([PROJECT])
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
    render(<PlanningPanel />)
    expect(await screen.findByText('1 blocked')).toBeTruthy()
  })
})
