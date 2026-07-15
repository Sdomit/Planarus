import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ExternalClientsPanel from './ExternalClientsPanel'

vi.mock('../api/client', () => ({
  api: {
    workspaces: { list: vi.fn() },
    projects: { list: vi.fn() },
    apiClients: { list: vi.fn(), create: vi.fn(), revoke: vi.fn() },
  },
}))

import { api } from '../api/client'

const mockApi = api as unknown as {
  workspaces: { list: ReturnType<typeof vi.fn> }
  projects: { list: ReturnType<typeof vi.fn> }
  apiClients: {
    list: ReturnType<typeof vi.fn>
    create: ReturnType<typeof vi.fn>
    revoke: ReturnType<typeof vi.fn>
  }
}

const WS = { id: 'ws_1', name: 'WS' }
const PROJ = { id: 'proj_1', title: 'Project One' }
const RAW = 'agbk_pubid123_secretvalue'

function created() {
  return {
    client: {
      id: 'apc_1', workspace_id: 'ws_1', key_id: 'pubid123', label: 'ci',
      can_read: true, can_propose: false, project_ids: ['proj_1'], enabled: true,
      created_at: '2026-06-21T00:00:00+00:00', expires_at: '2026-09-19T00:00:00+00:00',
      last_used_at: null, revoked_at: null,
    },
    api_key: RAW,
    warning: 'Copy and store this API key now',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn())
  vi.stubGlobal('confirm', vi.fn(() => true))
  mockApi.workspaces.list.mockResolvedValue([WS])
  mockApi.projects.list.mockResolvedValue([PROJ])
  mockApi.apiClients.list.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ExternalClientsPanel', () => {
  it('shows the loopback exposure warning', async () => {
    render(<ExternalClientsPanel onClose={vi.fn()} />)
    await waitFor(() => screen.getByText(/disabled by default/i))
    expect(screen.getByText(/loopback-bound/i)).toBeTruthy()
  })

  it('requires a project and at least one permission before create is enabled', async () => {
    render(<ExternalClientsPanel onClose={vi.fn()} />)
    await waitFor(() => screen.getByText(/No external API keys/i))
    fireEvent.click(screen.getByText('+ New key'))
    // Label + project still missing → disabled.
    const createBtn = screen.getByRole('button', { name: 'Create key' })
    expect((createBtn as HTMLButtonElement).disabled).toBe(true)

    fireEvent.change(screen.getByPlaceholderText('e.g. ci-readonly'), { target: { value: 'ci' } })
    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[]
    // [0]=project, [1]=can_read (default checked), [2]=can_propose
    fireEvent.click(checkboxes[0]) // select project
    expect((screen.getByRole('button', { name: 'Create key' }) as HTMLButtonElement).disabled).toBe(false)

    // Removing all permissions disables it again.
    fireEvent.click(checkboxes[1]) // uncheck can_read (was default)
    expect((screen.getByRole('button', { name: 'Create key' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('creates with default 90-day expiry and shows the key exactly once', async () => {
    mockApi.apiClients.create.mockResolvedValue(created())
    const setItem = vi.spyOn(Storage.prototype, 'setItem')

    render(<ExternalClientsPanel onClose={vi.fn()} />)
    await waitFor(() => screen.getByText(/No external API keys/i))
    fireEvent.click(screen.getByText('+ New key'))
    fireEvent.change(screen.getByPlaceholderText('e.g. ci-readonly'), { target: { value: 'ci' } })
    fireEvent.click((screen.getAllByRole('checkbox') as HTMLInputElement[])[0])
    fireEvent.click(screen.getByRole('button', { name: 'Create key' }))

    await waitFor(() => expect(mockApi.apiClients.create).toHaveBeenCalled())
    const payload = mockApi.apiClients.create.mock.calls[0][0]
    expect(payload.expires_in_days).toBe(90)
    expect(payload.project_ids).toEqual(['proj_1'])
    expect(payload.can_read).toBe(true)

    // The raw key is shown once in the modal.
    await waitFor(() => screen.getByText(RAW))
    // …and never written to storage.
    expect(setItem).not.toHaveBeenCalledWith(expect.anything(), expect.stringContaining(RAW))

    // Closing the modal clears the key from the DOM.
    fireEvent.click(screen.getByText('Done'))
    await waitFor(() => expect(screen.queryByText(RAW)).toBeNull())
  })

  it('revokes a key via the api helper (with confirmation)', async () => {
    mockApi.apiClients.list.mockResolvedValue([created().client])
    mockApi.apiClients.revoke.mockResolvedValue({ ...created().client, revoked_at: 'now' })
    render(<ExternalClientsPanel onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('ci'))
    fireEvent.click(screen.getByText('Revoke'))
    await waitFor(() => expect(mockApi.apiClients.revoke).toHaveBeenCalledWith('apc_1'))
  })

  it('shows project scope, expiry, and last-use safety metadata', async () => {
    mockApi.apiClients.list.mockResolvedValue([created().client])
    render(<ExternalClientsPanel onClose={vi.fn()} />)
    expect(await screen.findByText(/1 project: Project One/)).toBeTruthy()
    expect(screen.getByText(/Expires/)).toBeTruthy()
    expect(screen.getByText(/Never used/)).toBeTruthy()
    expect(screen.queryByText('1p')).toBeNull()
  })

  it('makes no direct network (fetch) request', async () => {
    mockApi.apiClients.create.mockResolvedValue(created())
    render(<ExternalClientsPanel onClose={vi.fn()} />)
    await waitFor(() => screen.getByText(/No external API keys/i))
    fireEvent.click(screen.getByText('+ New key'))
    fireEvent.change(screen.getByPlaceholderText('e.g. ci-readonly'), { target: { value: 'ci' } })
    fireEvent.click((screen.getAllByRole('checkbox') as HTMLInputElement[])[0])
    fireEvent.click(screen.getByRole('button', { name: 'Create key' }))
    await waitFor(() => expect(mockApi.apiClients.create).toHaveBeenCalled())
    expect(fetch as unknown as ReturnType<typeof vi.fn>).not.toHaveBeenCalled()
  })
})
