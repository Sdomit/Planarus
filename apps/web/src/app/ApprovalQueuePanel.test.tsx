import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ApprovalQueuePanel from './ApprovalQueuePanel'

vi.mock('../api/client', () => ({
  api: {
    approvals: {
      list: vi.fn(),
      listPaged: vi.fn(),
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
    listPaged: ReturnType<typeof vi.fn>
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
  decided_by_display: null,
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
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: ([PENDING]).length, hasMore: false })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    expect(screen.getByText(/Pending \(1\)/)).toBeTruthy()
    expect(screen.getByText(/History \(0\)/)).toBeTruthy()
  })

  it('#183 step 3: clicking a row calls onSelect with its id, for the URL to follow', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: 1, hasMore: false })
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    const onSelect = vi.fn()
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} onSelect={onSelect} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('apr_1'))
  })

  it('#183 step 3: initialApprovalId opens that detail on mount, for a deep link', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: 1, hasMore: false })
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} initialApprovalId="apr_1" />)
    await waitFor(() => expect(mockApi.approvals.get).toHaveBeenCalledWith('apr_1'))
  })

  it('says so when the server clipped the list (#103)', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({
      items: [PENDING], total: 250, hasMore: true,
    })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    expect(screen.getByText(/most recent of 250/)).toBeTruthy()
  })

  it('stays silent when the list is complete', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({
      items: [PENDING], total: 1, hasMore: false,
    })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    expect(screen.queryByText(/most recent of/)).toBeNull()
  })

  it('shows who decided and named audit actors (P16.0)', async () => {
    const decided = {
      ...PENDING,
      status: 'approved',
      decided_at: '2026-06-20T11:00:00+00:00',
      decided_by: 'usr_1',
      decided_by_display: 'Alice Smith',
    }
    mockApi.approvals.listPaged.mockResolvedValue({ items: [decided], total: ([decided]).length, hasMore: false })
    mockApi.approvals.get.mockResolvedValue({ ...DETAIL, ...decided })
    mockApi.approvals.audit.mockResolvedValue([
      {
        id: 'aud_1',
        event_type: 'proposal_approved',
        actor_type: 'human',
        actor_id: 'usr_1',
        actor_display: 'Alice Smith',
        created_at: '2026-06-20T11:00:00+00:00',
      },
    ])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => screen.getByText('Decided by'))
    // Name appears in the meta row and again in the audit timeline.
    expect(screen.getAllByText('Alice Smith').length).toBe(2)
  })

  it('shows the field-level diff as text and the mandatory warning', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: ([PENDING]).length, hasMore: false })
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() =>
      expect(
        screen.getByText(
          /Approving allows Planarus to apply only this exact proposal once/i,
        ),
      ).toBeTruthy(),
    )
    expect(screen.getByText('title')).toBeTruthy()
    expect(screen.getByText('New task')).toBeTruthy()
    // No raw HTML rendering.
    expect(document.querySelector('[dangerouslysetinnerhtml]')).toBeNull()
  })

  it('approve is required before apply; both call the API', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: ([PENDING]).length, hasMore: false })
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
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: ([PENDING]).length, hasMore: false })
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

  // --- #96: ergonomics of the surface that gates every agent write -----------

  it('shows the server-resolved target title instead of the raw id', async () => {
    const update = {
      ...PENDING,
      action_type: 'task.update',
      target_entity_id: 'tsk_1a2b3c4d5e6f7890',
      target_title: 'Ship the thing',
    }
    mockApi.approvals.listPaged.mockResolvedValue({ items: [update], total: 1, hasMore: false })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.update'))
    expect(screen.getByText('Ship the thing')).toBeTruthy()
    expect(screen.queryByText(/tsk_1a2b3c4d5e6f/)).toBeNull()
  })

  it('falls back to the id when the target has no resolved title', async () => {
    const update = {
      ...PENDING,
      action_type: 'task.update',
      target_entity_id: 'tsk_1a2b3c4d5e6f7890',
      target_title: null,
    }
    mockApi.approvals.listPaged.mockResolvedValue({ items: [update], total: 1, hasMore: false })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.update'))
    expect(screen.getByText(/task:tsk_1a2b3c4d/)).toBeTruthy()
  })

  it('approve & apply is one click and still calls both endpoints', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: 1, hasMore: false })
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    mockApi.approvals.approve.mockResolvedValue({ ...PENDING, status: 'approved' })
    mockApi.approvals.apply.mockResolvedValue({ ...PENDING, status: 'applied' })

    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => screen.getByText('Approve & apply'))

    fireEvent.click(screen.getByText('Approve & apply'))
    await waitFor(() => expect(mockApi.approvals.apply).toHaveBeenCalledWith('apr_1'))
    // Approve is never skipped — apply still re-runs its stale-state checks.
    expect(mockApi.approvals.approve).toHaveBeenCalledWith('apr_1')
  })

  it('bulk-approves and applies every checked row', async () => {
    const second = { ...PENDING, id: 'apr_2', action_type: 'decision.create' }
    mockApi.approvals.listPaged.mockResolvedValue({
      items: [PENDING, second], total: 2, hasMore: false,
    })
    mockApi.approvals.approve.mockResolvedValue({ ...PENDING, status: 'approved' })
    mockApi.approvals.apply.mockResolvedValue({ ...PENDING, status: 'applied' })

    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))

    fireEvent.click(screen.getByLabelText('Select all pending proposals'))
    fireEvent.click(screen.getByText(/Approve & apply \(2\)/))

    await waitFor(() => expect(mockApi.approvals.apply).toHaveBeenCalledTimes(2))
    expect(mockApi.approvals.approve.mock.calls.map(c => c[0])).toEqual(['apr_1', 'apr_2'])
    expect(mockApi.approvals.apply.mock.calls.map(c => c[0])).toEqual(['apr_1', 'apr_2'])
  })

  it('a failing row in a bulk run is named and does not stop the rest', async () => {
    const second = { ...PENDING, id: 'apr_2', action_type: 'decision.create' }
    mockApi.approvals.listPaged.mockResolvedValue({
      items: [PENDING, second], total: 2, hasMore: false,
    })
    mockApi.approvals.approve.mockResolvedValue({ ...PENDING, status: 'approved' })
    mockApi.approvals.apply.mockImplementation((id: string) =>
      id === 'apr_1' ? Promise.reject(new Error('target changed')) : Promise.resolve({ ...second, status: 'applied' }),
    )

    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByLabelText('Select all pending proposals'))
    fireEvent.click(screen.getByText(/Approve & apply \(2\)/))

    await waitFor(() => expect(screen.getByText(/target changed/)).toBeTruthy())
    // The second row still ran.
    expect(mockApi.approvals.apply).toHaveBeenCalledWith('apr_2')
  })

  it('offers no checkbox on decided history rows', async () => {
    const decided = { ...PENDING, id: 'apr_9', status: 'applied', action_type: 'risk.create' }
    mockApi.approvals.listPaged
      .mockResolvedValueOnce({ items: [PENDING], total: 1, hasMore: false })
      .mockResolvedValueOnce({ items: [PENDING, decided], total: 2, hasMore: false })

    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('risk.create'))
    expect(screen.getByText(/History \(1\)/)).toBeTruthy()
    // One row checkbox for the single pending row, plus the select-all box.
    expect(document.querySelectorAll('.aqp-check').length).toBe(1)
  })

  it('polls the list so proposals raised while you watch appear', async () => {
    vi.useFakeTimers()
    try {
      mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: 1, hasMore: false })
      render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
      // Two calls per load: the open-status page and the unfiltered page.
      await vi.waitFor(() => expect(mockApi.approvals.listPaged).toHaveBeenCalledTimes(2))
      await vi.advanceTimersByTimeAsync(60_000)
      expect(mockApi.approvals.listPaged).toHaveBeenCalledTimes(4)
    } finally {
      vi.useRealTimers()
    }
  })

  it('puts the rejection reason above the buttons, not below them', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: 1, hasMore: false })
    mockApi.approvals.get.mockResolvedValue(DETAIL)
    mockApi.approvals.audit.mockResolvedValue([])
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('task.create'))
    fireEvent.click(screen.getByText('task.create'))
    await waitFor(() => screen.getByPlaceholderText('Optional rejection reason'))

    const reason = screen.getByPlaceholderText('Optional rejection reason')
    const reject = screen.getByText('Reject')
    // DOCUMENT_POSITION_FOLLOWING (4) — the buttons come after the input.
    expect(reason.compareDocumentPosition(reject) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('makes no direct network (fetch) request', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [PENDING], total: ([PENDING]).length, hasMore: false })
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

  it('teaches the loop when nothing is waiting (#159)', async () => {
    mockApi.approvals.listPaged.mockResolvedValue({ items: [], total: 0, hasMore: false })
    render(<ApprovalQueuePanel projectId="proj_1" onClose={vi.fn()} />)
    // Was a bare "No pending proposals." — the queue is the product's whole
    // loop, and its empty state never said how a proposal would arrive.
    await waitFor(() => screen.getByText('No proposals waiting'))
    expect(screen.getByText(/when a connected agent suggests a change/)).toBeTruthy()
    expect(screen.getByText(/Settings → Integrations/)).toBeTruthy()
  })
})
