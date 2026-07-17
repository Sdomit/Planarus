import { describe, it, expect } from 'vitest'
import { moveBefore } from './useListReorder'

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
