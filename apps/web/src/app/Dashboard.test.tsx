import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import Dashboard from './Dashboard'
import { api, Project } from '../api/client'

const baseProject: Project = {
  id: 'proj_1',
  workspace_id: 'ws_1',
  title: 'Old Title',
  slug: 'old-title',
  summary: null,
  project_type: null,
  status: 'idea',
  priority: null,
  folder_path: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
  archived_at: null,
}

vi.mock('../api/client', () => ({
  api: {
    workspaces: { list: vi.fn(), create: vi.fn() },
    projects: {
      list: vi.fn(), create: vi.fn(), update: vi.fn(), duplicate: vi.fn(),
      archive: vi.fn(), unarchive: vi.fn(), remove: vi.fn(),
    },
    tasks: { list: vi.fn() },
    risks: { list: vi.fn() },
    approvals: { list: vi.fn(), listPaged: vi.fn() },
  },
}))

function mockProject(overrides: Partial<Project> = {}) {
  vi.mocked(api.projects.list).mockResolvedValue([{ ...baseProject, ...overrides }])
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(api.workspaces.list).mockResolvedValue([
    {
      id: 'ws_1', name: 'Default', slug: 'default', description: null,
      default_project_root: null, created_at: 't', updated_at: 't',
    },
  ])
  vi.mocked(api.projects.update).mockReset().mockResolvedValue(baseProject)
  vi.mocked(api.tasks.list).mockResolvedValue([])
  vi.mocked(api.risks.list).mockResolvedValue([])
  vi.mocked(api.approvals.list).mockResolvedValue([])
  vi.mocked(api.approvals.listPaged).mockResolvedValue({ items: [], total: 0, hasMore: false })
  mockProject()
})

afterEach(cleanup)

/** Open the card's ⋯ menu and pick "Edit details…". */
async function openEditModal() {
  fireEvent.click(await screen.findByRole('button', { name: 'Project actions' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Edit details…' }))
  return screen.getByLabelText('Title') as HTMLInputElement
}

describe('Dashboard project edit (#158)', () => {
  it('renders a priority badge when the project carries one', async () => {
    mockProject({ priority: 'high' })
    render(<Dashboard />)
    expect(await screen.findByText('high')).toBeTruthy()
  })

  it('prefills the edit form from the project and PATCHes title, summary and priority', async () => {
    mockProject({ summary: 'Old summary', priority: 'low' })
    render(<Dashboard />)
    const title = await openEditModal()
    expect(title.value).toBe('Old Title')
    expect((screen.getByLabelText('Summary') as HTMLInputElement).value).toBe('Old summary')
    expect((screen.getByLabelText('Priority') as HTMLSelectElement).value).toBe('low')

    fireEvent.change(title, { target: { value: 'New Title' } })
    fireEvent.change(screen.getByLabelText('Summary'), { target: { value: 'New summary' } })
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'urgent' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(api.projects.update).toHaveBeenCalledWith('proj_1', {
      title: 'New Title', summary: 'New summary', priority: 'urgent',
    }))
    // The modal closes and the list is reloaded from the server.
    await waitFor(() => expect(screen.queryByText('Edit project')).toBeNull())
    expect(vi.mocked(api.projects.list).mock.calls.length).toBeGreaterThan(1)
  })

  it('clears summary and priority with null rather than an empty string', async () => {
    mockProject({ summary: 'Old summary', priority: 'med' })
    render(<Dashboard />)
    await openEditModal()
    fireEvent.change(screen.getByLabelText('Summary'), { target: { value: '   ' } })
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(api.projects.update).toHaveBeenCalledWith('proj_1', {
      title: 'Old Title', summary: null, priority: null,
    }))
  })

  it('keeps the form open with the entered values when the save fails', async () => {
    vi.mocked(api.projects.update).mockRejectedValue(new Error('API error 403: forbidden'))
    render(<Dashboard />)
    const title = await openEditModal()
    fireEvent.change(title, { target: { value: 'Half-typed rename' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    // The failure surfaces inside the modal, not as a page-level banner that
    // would unmount the form and discard the edit.
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('403'))
    expect(screen.getByText('Edit project')).toBeTruthy()
    expect((screen.getByLabelText('Title') as HTMLInputElement).value).toBe('Half-typed rename')
    // Retry is possible: the button is live again.
    expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('will not submit a blank title', async () => {
    render(<Dashboard />)
    const title = await openEditModal()
    fireEvent.change(title, { target: { value: '  ' } })
    const save = screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.click(save)
    expect(api.projects.update).not.toHaveBeenCalled()
  })
})

describe('Dashboard project delete', () => {
  it('offers delete on a live project and gates it behind typing the title', async () => {
    vi.mocked(api.projects.remove).mockResolvedValue(undefined)
    render(<Dashboard />)
    fireEvent.click(await screen.findByRole('button', { name: 'Project actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete permanently…' }))

    const confirm = screen.getByRole('button', { name: 'Delete permanently' }) as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.click(confirm)
    expect(api.projects.remove).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'Not The Title' } })
    expect((screen.getByRole('button', { name: 'Delete permanently' }) as HTMLButtonElement).disabled).toBe(true)

    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'Old Title' } })
    fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(api.projects.remove).toHaveBeenCalledWith('proj_1'))
  })

  it('cancelling leaves the project alone', async () => {
    vi.mocked(api.projects.remove).mockReset()   // the file's beforeEach only resets update()
    render(<Dashboard />)
    fireEvent.click(await screen.findByRole('button', { name: 'Project actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete permanently…' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByText('Delete project permanently')).toBeNull()
    expect(api.projects.remove).not.toHaveBeenCalled()
  })
})
