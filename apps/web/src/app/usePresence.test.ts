import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { usePresence } from './usePresence'
import { api, type PresenceView } from '../api/client'

vi.mock('../api/client', () => ({
  api: { docs: { presenceBeat: vi.fn(), presenceLeave: vi.fn() } },
}))

const view = (over: Partial<PresenceView> = {}): PresenceView => ({
  entries: [
    { user_id: 'u1', display_name: 'Ana', mode: 'editing', idle_seconds: 0 },
    { user_id: 'u2', display_name: 'Ben', mode: 'editing', idle_seconds: 1 },
  ],
  editor_user_id: 'u1',
  you: 'u2',
  ttl_seconds: 30,
  ...over,
})

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(api.docs.presenceLeave).mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

describe('usePresence', () => {
  it('locks when someone else holds the editing claim', async () => {
    vi.mocked(api.docs.presenceBeat).mockResolvedValue(view())
    const { result } = renderHook(() => usePresence('d1', true))
    await flush()
    expect(result.current.active).toBe(true)
    expect(result.current.lockedByOther).toBe(true)
    expect(result.current.editorName).toBe('Ana')
    expect(api.docs.presenceBeat).toHaveBeenCalledWith('d1', 'editing')
  })

  it('does not lock when the caller is the editor', async () => {
    vi.mocked(api.docs.presenceBeat).mockResolvedValue(view({ you: 'u1' }))
    const { result } = renderHook(() => usePresence('d1', true))
    await flush()
    expect(result.current.lockedByOther).toBe(false)
    expect(result.current.editorName).toBeNull()
  })

  it('keeps beating on an interval and leaves on unmount', async () => {
    vi.mocked(api.docs.presenceBeat).mockResolvedValue(view({ you: 'u1' }))
    const { unmount } = renderHook(() => usePresence('d1', true))
    await flush()
    expect(api.docs.presenceBeat).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(api.docs.presenceBeat).toHaveBeenCalledTimes(2)
    unmount()
    expect(api.docs.presenceLeave).toHaveBeenCalledWith('d1')
  })

  it('goes dormant on 404 (local mode): no more beats, no leave call', async () => {
    vi.mocked(api.docs.presenceBeat).mockRejectedValue(new Error('404: not found'))
    const { result, unmount } = renderHook(() => usePresence('d1', true))
    await flush()
    expect(result.current.active).toBe(false)
    expect(result.current.lockedByOther).toBe(false)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(api.docs.presenceBeat).toHaveBeenCalledTimes(1)
    unmount()
    expect(api.docs.presenceLeave).not.toHaveBeenCalled()
  })

  it('survives a transient error and retries next tick', async () => {
    vi.mocked(api.docs.presenceBeat)
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValue(view())
    const { result } = renderHook(() => usePresence('d1', true))
    await flush()
    expect(result.current.active).toBe(false)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(result.current.active).toBe(true)
    expect(result.current.editorName).toBe('Ana')
  })
})
