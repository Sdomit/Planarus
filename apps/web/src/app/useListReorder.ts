import { useState } from 'react'
import type React from 'react'

/** Move `dragId` so it sits at `targetId`'s position (works both directions). */
export function moveBefore<T extends { id: string }>(items: T[], dragId: string, targetId: string): T[] {
  if (dragId === targetId) return items
  const from = items.findIndex(i => i.id === dragId)
  if (from < 0 || items.findIndex(i => i.id === targetId) < 0) return items
  const arr = [...items]
  const [moved] = arr.splice(from, 1)
  const insertAt = arr.findIndex(i => i.id === targetId)
  arr.splice(insertAt, 0, moved)
  return arr
}

/**
 * HTML5 drag-to-reorder for a flat list. `apply` sets the caller's state
 * (optimistic); `persist` sends the new id order to the API and, on failure,
 * the previous order is restored. Spread `itemProps(id)` onto each row.
 */
export function useListReorder<T extends { id: string }>(
  items: T[],
  apply: (ordered: T[]) => void,
  persist: (ids: string[]) => Promise<T[] | void>,
) {
  const [dragId, setDragId] = useState<string | null>(null)
  const [overId, setOverId] = useState<string | null>(null)

  /** Move `id` to sit at `targetId`'s position and persist the new order. */
  async function reorder(id: string, targetId: string) {
    if (id === targetId) return
    const prev = items
    const next = moveBefore(items, id, targetId)
    apply(next)
    try {
      const saved = await persist(next.map(i => i.id))
      if (Array.isArray(saved)) apply(saved)
    } catch (err) {
      // Roll the optimistic move back. Reorder persists the whole id set, so a
      // failure here means the set changed under us (a concurrent add/remove) or
      // the request was rejected — don't leave it silent. Callers must pass the
      // full list, never a filtered subset (that would persist a partial set). #86
      apply(prev)
      console.error('reorder failed to persist; order reverted', err)
    }
  }

  /**
   * Move `id` one slot up (-1) or down (+1).
   *
   * The touch- and keyboard-reachable equivalent of dragging: HTML5 drag events
   * never fire on iOS or Android, so without this a list can only be reordered
   * with a mouse.
   *
   * Note the asymmetry — it is not a typo. `moveBefore` removes the item first,
   * so "insert at the next item's position" lands it right back where it was.
   * Moving DOWN is therefore expressed as moving the next item UP past this one.
   */
  async function moveBy(id: string, delta: -1 | 1) {
    const from = items.findIndex(i => i.id === id)
    if (from < 0) return
    const to = from + delta
    if (to < 0 || to >= items.length) return
    if (delta < 0) await reorder(id, items[to].id)
    else await reorder(items[to].id, id)
  }

  async function drop(targetId: string) {
    const id = dragId
    setOverId(null)
    setDragId(null)
    if (!id) return
    await reorder(id, targetId)
  }

  const itemProps = (id: string) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => { e.stopPropagation(); setDragId(id) },
    onDragEnd: () => { setDragId(null); setOverId(null) },
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); if (overId !== id) setOverId(id) },
    onDrop: (e: React.DragEvent) => { e.preventDefault(); void drop(id) },
    'data-over': overId === id ? '' : undefined,
    'data-dragging': dragId === id ? '' : undefined,
  })

  return { dragId, overId, itemProps, reorder, moveBy }
}
