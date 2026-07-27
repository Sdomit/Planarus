import { describe, it, expect, vi } from 'vitest'
import { badgeText, fetchPendingTotal, nextDelayMinutes, EXTERNAL_BASE } from '../../../extension/badge.js'

/**
 * The pending-approval badge (#108, slice 18.2) is the one part of the
 * extension with logic worth pinning outside a service worker — same reason
 * `extension-contract.test.ts` exists for capture-url.js. `fetchImpl` is
 * always a mock here; nothing in this file makes a real network call.
 */

const API = 'http://localhost:8000'
const KEY = 'agbk_test_key'

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: () => Promise.resolve(body) }
}

function mockFetch(byUrl: Record<string, unknown>) {
  return vi.fn((url: string) => {
    if (url in byUrl) return Promise.resolve(jsonResponse(byUrl[url]))
    return Promise.resolve(jsonResponse({}, false, 404))
  })
}

describe('badgeText (#108)', () => {
  it('clears the badge at zero or below — Chrome\'s own "no badge" contract', () => {
    expect(badgeText(0)).toBe('')
    expect(badgeText(-1)).toBe('')
    expect(badgeText(NaN)).toBe('')
  })

  it('shows the exact count for anything readable on a toolbar badge', () => {
    expect(badgeText(1)).toBe('1')
    expect(badgeText(42)).toBe('42')
    expect(badgeText(99)).toBe('99')
  })

  it('caps at 99+ rather than overflowing the badge', () => {
    expect(badgeText(100)).toBe('99+')
    expect(badgeText(4000)).toBe('99+')
  })
})

describe('nextDelayMinutes (#108 AC5: backoff when unreachable)', () => {
  it('polls at the normal cadence with no failures', () => {
    expect(nextDelayMinutes(0)).toBe(1)
  })

  it('doubles per consecutive failure', () => {
    expect(nextDelayMinutes(1)).toBe(2)
    expect(nextDelayMinutes(2)).toBe(4)
    expect(nextDelayMinutes(3)).toBe(8)
  })

  it('caps the backoff rather than growing unbounded', () => {
    expect(nextDelayMinutes(10)).toBe(30)
    expect(nextDelayMinutes(1000)).toBe(30)
  })
})

describe('fetchPendingTotal (#108 AC1/AC3: sum across scope, degrade quietly)', () => {
  it('never calls the network with no url/key configured', async () => {
    const fetchImpl = vi.fn()
    expect(await fetchPendingTotal(undefined, undefined, fetchImpl)).toEqual({ ok: false, count: 0 })
    expect(await fetchPendingTotal(API, '', fetchImpl)).toEqual({ ok: false, count: 0 })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('sums pending_count across every project the key can see', async () => {
    const fetchImpl = mockFetch({
      [`${API}${EXTERNAL_BASE}/projects`]: { metadata: { project_ids: ['p1', 'p2'] } },
      [`${API}${EXTERNAL_BASE}/projects/p1/approvals/pending-count`]: { metadata: { pending_count: 2 } },
      [`${API}${EXTERNAL_BASE}/projects/p2/approvals/pending-count`]: { metadata: { pending_count: 3 } },
    })
    expect(await fetchPendingTotal(API, KEY, fetchImpl)).toEqual({ ok: true, count: 5 })
  })

  it('sends the key as a bearer token on every request', async () => {
    const fetchImpl = mockFetch({
      [`${API}${EXTERNAL_BASE}/projects`]: { metadata: { project_ids: [] } },
    })
    await fetchPendingTotal(API, KEY, fetchImpl)
    expect(fetchImpl).toHaveBeenCalledWith(
      `${API}${EXTERNAL_BASE}/projects`,
      { headers: { Authorization: `Bearer ${KEY}` } },
    )
  })

  it('degrades to ok:false on a 401/403/404 — a revoked, wrong-scope or missing key', async () => {
    const fetchImpl = mockFetch({}) // nothing matches -> 404 from the helper above
    expect(await fetchPendingTotal(API, KEY, fetchImpl)).toEqual({ ok: false, count: 0 })
  })

  it('degrades to ok:false rather than throwing when the network itself fails', async () => {
    const fetchImpl = vi.fn(() => Promise.reject(new Error('offline')))
    expect(await fetchPendingTotal(API, KEY, fetchImpl)).toEqual({ ok: false, count: 0 })
  })

  it('degrades to ok:false on an unrecognisable response shape', async () => {
    const fetchImpl = mockFetch({ [`${API}${EXTERNAL_BASE}/projects`]: { metadata: {} } })
    expect(await fetchPendingTotal(API, KEY, fetchImpl)).toEqual({ ok: false, count: 0 })
  })

  it('treats a missing/non-numeric pending_count as zero, not NaN', async () => {
    const fetchImpl = mockFetch({
      [`${API}${EXTERNAL_BASE}/projects`]: { metadata: { project_ids: ['p1'] } },
      [`${API}${EXTERNAL_BASE}/projects/p1/approvals/pending-count`]: { metadata: {} },
    })
    expect(await fetchPendingTotal(API, KEY, fetchImpl)).toEqual({ ok: true, count: 0 })
  })
})
