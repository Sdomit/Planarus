import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, _resetLocalTokenForTests } from './client'

interface Call {
  url: string
  init?: RequestInit
}

function fakeResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

beforeEach(() => {
  _resetLocalTokenForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiClients client uses local control token', () => {
  it('attaches the local token to create and revoke', async () => {
    const calls: Call[] = []
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.endsWith('/local-session')) return fakeResponse({ token: 'LTOK' })
      return fakeResponse({ id: 'apc_1', client: { id: 'apc_1' }, api_key: 'agbk_a_b' })
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.apiClients.create({
      label: 'l', workspace_id: 'ws_1', project_ids: ['p1'], can_read: true, can_propose: false,
    })
    const createCall = calls.find((c) => c.url.endsWith('/api-clients'))
    const ch = (createCall?.init?.headers ?? {}) as Record<string, string>
    expect(ch['X-AgentBoard-Local-Token']).toBe('LTOK')

    await api.apiClients.revoke('apc_1')
    const revokeCall = calls.find((c) => c.url.includes('/revoke'))
    const rh = (revokeCall?.init?.headers ?? {}) as Record<string, string>
    expect(rh['X-AgentBoard-Local-Token']).toBe('LTOK')

    // Token fetched once and reused.
    expect(calls.filter((c) => c.url.endsWith('/local-session')).length).toBe(1)
  })

  it('list is also local-control-gated (token attached)', async () => {
    const calls: Call[] = []
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.endsWith('/local-session')) return fakeResponse({ token: 'LTOK' })
      return fakeResponse([])
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.apiClients.list('ws_1')
    const listCall = calls.find((c) => c.url.includes('/api-clients?'))
    const lh = (listCall?.init?.headers ?? {}) as Record<string, string>
    expect(lh['X-AgentBoard-Local-Token']).toBe('LTOK')
  })
})
