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
    } catch {
      apply(prev)
    }
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

  return { dragId, overId, itemProps, reorder }
}
