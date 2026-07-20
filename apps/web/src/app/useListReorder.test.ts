import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { moveBefore, useListReorder } from './useListReorder'

const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }]

describe('moveBefore', () => {
  it('moves an item forward to the target position', () => {
    expect(moveBefore(items, 'a', 'c').map(i => i.id)).toEqual(['b', 'a', 'c', 'd'])
  })

  it('moves an item backward to the target position', () => {
    expect(moveBefore(items, 'd', 'b').map(i => i.id)).toEqual(['a', 'd', 'b', 'c'])
  })

  it('is a no-op when drag === target', () => {
    expect(moveBefore(items, 'b', 'b')).toBe(items)
  })

  it('is a no-op for unknown ids', () => {
    expect(moveBefore(items, 'z', 'b')).toBe(items)
  })
})

// moveBy is the touch/keyboard path — HTML5 drag events never fire on mobile.
// Its up/down branches are deliberately asymmetric, which is exactly the kind
// of thing that silently regresses into a no-op, so pin both directions.
describe('useListReorder.moveBy', () => {
  const setup = () => {
    const apply = vi.fn()
    const persist = vi.fn().mockResolvedValue(undefined)
    const hook = renderHook(() => useListReorder(items, apply, persist))
    return { apply, persist, hook }
  }
  const orderAfter = (apply: ReturnType<typeof vi.fn>) =>
    (apply.mock.calls[0][0] as { id: string }[]).map(i => i.id)

  it('moves an item down one slot', async () => {
    const { apply, hook } = setup()
    await act(async () => { await hook.result.current.moveBy('a', 1) })
    expect(orderAfter(apply)).toEqual(['b', 'a', 'c', 'd'])
  })

  it('moves an item up one slot', async () => {
    const { apply, hook } = setup()
    await act(async () => { await hook.result.current.moveBy('c', -1) })
    expect(orderAfter(apply)).toEqual(['a', 'c', 'b', 'd'])
  })

  it('does nothing at the boundaries', async () => {
    const { apply, hook } = setup()
    await act(async () => { await hook.result.current.moveBy('a', -1) })
    await act(async () => { await hook.result.current.moveBy('d', 1) })
    expect(apply).not.toHaveBeenCalled()
  })

  it('restores the previous order when persisting fails', async () => {
    const apply = vi.fn()
    const persist = vi.fn().mockRejectedValue(new Error('offline'))
    const hook = renderHook(() => useListReorder(items, apply, persist))
    await act(async () => { await hook.result.current.moveBy('a', 1) })
    expect(apply).toHaveBeenCalledTimes(2)
    expect((apply.mock.calls[1][0] as { id: string }[]).map(i => i.id))
      .toEqual(['a', 'b', 'c', 'd'])
  })
})
