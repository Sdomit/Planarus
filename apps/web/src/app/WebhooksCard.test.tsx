import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import WebhooksCard from './WebhooksCard'

const list = vi.fn()
const create = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    workspaces: { list: vi.fn(async () => [{ id: 'ws_1', name: 'WS' }]) },
    webhooks: {
      list: (...a: unknown[]) => list(...a),
      create: (...a: unknown[]) => create(...a),
      remove: vi.fn(async () => undefined),
      deliveries: vi.fn(async () => []),
      test: vi.fn(async () => ({})),
      redeliver: vi.fn(async () => ({})),
    },
  },
}))

vi.mock('./format', () => ({ fmtTimestamp: (s: string) => s }))

afterEach(() => { cleanup(); vi.clearAllMocks() })

const SUB = {
  id: 'whs_1', workspace_id: 'ws_1', target_url: 'https://a/hook',
  event_kinds: [], project_ids: [], format: 'json', enabled: true,
  failure_count: 0, created_at: 't', disabled_at: null,
}

describe('WebhooksCard', () => {
  it('lists subscriptions for the selected workspace', async () => {
    list.mockResolvedValue([SUB])
    render(<WebhooksCard />)
    await waitFor(() => expect(screen.getByText('https://a/hook')).toBeTruthy())
  })

  it('creates a webhook and reveals the signing secret exactly once', async () => {
    list.mockResolvedValue([])
    create.mockResolvedValue({ subscription: { ...SUB, id: 'whs_2' }, secret: 'whsec_top_secret' })
    render(<WebhooksCard />)
    await waitFor(() => screen.getByLabelText('Target URL'))
    fireEvent.change(screen.getByLabelText('Target URL'), { target: { value: 'https://b/hook' } })
    fireEvent.click(screen.getByRole('button', { name: '+ Add webhook' }))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(expect.objectContaining({ target_url: 'https://b/hook', format: 'json' })),
    )
    expect(await screen.findByText('whsec_top_secret')).toBeTruthy()
  })

  it('shows the inert note when webhooks are not configured (404)', async () => {
    list.mockRejectedValue(new Error('404: not found'))
    render(<WebhooksCard />)
    await waitFor(() => expect(screen.getByText(/PLANARUS_WEBHOOK_ENC_KEY/)).toBeTruthy())
  })
})
