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

describe('approvals client local control token', () => {
  it('attaches the token to state-changing calls and fetches it once', async () => {
    const calls: Call[] = []
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.endsWith('/local-session')) return fakeResponse({ token: 'TOK123' })
      return fakeResponse({ id: 'apr_1', status: 'approved' })
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.approvals.approve('apr_1')

    expect(calls.some((c) => c.url.includes('/local-session'))).toBe(true)
    const approveCall = calls.find((c) => c.url.includes('/approve'))
    const headers = (approveCall?.init?.headers ?? {}) as Record<string, string>
    expect(headers['X-Approvo-Local-Token']).toBe('TOK123')

    // A second state-changing call reuses the cached token (no second fetch).
    await api.approvals.apply('apr_1')
    const sessionFetches = calls.filter((c) => c.url.includes('/local-session'))
    expect(sessionFetches.length).toBe(1)
  })

  it('does not attach the token (or fetch a session) for read-only GETs', async () => {
    const calls: Call[] = []
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return fakeResponse([])
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.approvals.list('proj_1')

    expect(calls.some((c) => c.url.includes('/local-session'))).toBe(false)
    const listCall = calls.find((c) => c.url.includes('/approvals'))
    const headers = (listCall?.init?.headers ?? {}) as Record<string, string>
    expect(headers['X-Approvo-Local-Token']).toBeUndefined()
  })
})
