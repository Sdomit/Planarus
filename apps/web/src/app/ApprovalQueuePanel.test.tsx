import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ApprovalQueuePanel from './ApprovalQueuePanel'

vi.mock('../api/client', () => ({
  api: {
    approvals: {
      list: vi.fn(),
      get: vi.fn(),
      audit: vi.fn(),
      approve: vi.fn(),
      apply: vi.fn(),
      reject: vi.fn(),
      invalidate: vi.fn(),
    },
  },
}))

import { api } from '../api/client'

const mockApi = api as unknown as {
  approvals: {
    list: ReturnType<typeof vi.fn>
    get: ReturnType<typeof vi.fn>
    audit: ReturnType<typeof vi.fn>
    approve: ReturnType<typeof vi.fn>
    apply: ReturnType<typeof vi.fn>
    reject: ReturnType<typeof vi.fn>
    invalidate: ReturnType<typeof vi.fn>
  }
}

const PENDING = {
  id: 'apr_1',
  workspace_id: 'ws_1',
  project_id: 'proj_1',
  origin: 'local',
  actor_ref: null,
  action_type: 'task.create',
  target_entity_type: 'task',
  target_entity_id: null,
  risk_level: 'low',
  status: 'pending',
  policy_version: 1,
  created_at: '2026-06-20T10:00:00+00:00',
  expires_at: '2026-06-21T10:00:00+00:00',
  decided_at: null,
  decided_by: null,
  applied_at: null,
  reason: null,
  failure_reason: null,
}

const DETAIL = {
  ...PENDING,
  patch_checksum: 'abcdef0123456789aa',
  diff: [{ field: 'title', before: null, after: 'New task' }],
  is_expired: false,
  stale_reason: null,
  secret_warning: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ApprovalQueuePanel', () => {
  it('renders a pending proposal in the queue', async () => {
    mockApi.approvals.list.mockResolvedValue([PENDING])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    expect(screen.getByText(/Pending \(1\)/)).toBeTruthy()
    expect(screen.getByText(/History \(0\)/)).toBeTruthy()
  })

  it('shows the field-level diff as text and the mandatory warning', async () => {
    mockApi.approvals.list.mockResolvedValue([PENDING])
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() =>
      expect(
        screen.getByText(
          /Approving allows AgentBoard to apply only this exact proposal once/i,
        ),
      ).toBeTruthy(),
    )
    expect(screen.getByText('title')).toBeTruthy()
    expect(screen.getByText('New task')).toBeTruthy()
    // No raw HTML rendering.
    expect(document.querySelector('[dangerouslysetinnerhtml]')).toBeNull()
  })

  it('approve is required before apply; both call the API', async () => {
    mockApi.approvals.list.mockResolvedValue([PENDING])
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    mockApi.approvals.approve.mockResolvedValue({ ...PENDING, status: 'approved' })
    mockApi.approvals.apply.mockResolvedValue({ ...PENDING, status: 'applied' })

    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => screen.getByText('Approve'))

    // Apply is not available until approved.
    expect(screen.queryByText('Apply')).toBeNull()

    fireEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(mockApi.approvals.approve).toHaveBeenCalledWith('apr_1'))

    await waitFor(() => screen.getByText('Apply'))
    fireEvent.click(screen.getByText('Apply'))
    await waitFor(() => expect(mockApi.approvals.apply).toHaveBeenCalledWith('apr_1'))
  })

  it('surfaces stale and expired warnings', async () => {
    mockApi.approvals.list.mockResolvedValue([PENDING])
    mockApi.approvals.get.mockResolvedValue({
      ...DETAIL,
      is_expired: true,
      stale_reason: 'target changed since proposal',
    })
    mockApi.approvals.audit.mockResolvedValue([])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => expect(screen.getByText(/has expired/i)).toBeTruthy())
    expect(screen.getByText(/target changed since proposal/i)).toBeTruthy()
    // The secret-policy note is always shown.
    expect(screen.getByText(/Secrets are blocked at proposal time/i)).toBeTruthy()
  })

  it('has no bulk approve/apply controls', async () => {
    mockApi.approvals.list.mockResolvedValue([PENDING])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    expect(screen.queryByText(/approve all/i)).toBeNull()
    expect(screen.queryByText(/apply all/i)).toBeNull()
    expect(screen.queryByText(/select all/i)).toBeNull()
    // No selection checkboxes on rows.
    expect(document.querySelectorAll('input[type="checkbox"]').length).toBe(0)
  })

  it('makes no direct network (fetch) request', async () => {
    mockApi.approvals.list.mockResolvedValue([PENDING])
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    mockApi.approvals.approve.mockResolvedValue({ ...PENDING, status: 'approved' })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => screen.getByText('Approve'))
    fireEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(mockApi.approvals.approve).toHaveBeenCalled())
    expect(fetch as unknown as ReturnType<typeof vi.fn>).not.toHaveBeenCalled()
  })
})
