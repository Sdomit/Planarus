import { useState } from 'react'
import type { ReactNode } from 'react'

export interface BoardCol {
  key: string
  label: string
  statuses: string[]
  dot: string
}

/** Status an item takes when dropped on `col`; null if it already fits (no write). */
export function nextStatusForColumn(itemStatus: string, col: Pick<BoardCol, 'statuses'>): string | null {
  return col.statuses.includes(itemStatus) ? null : col.statuses[0]
}

/**
 * A generic kanban board. Columns are supplied by the caller; dragging a card
 * to another column calls `onRestatus(item, newStatus)`. Dropping a card onto
 * another card in the same column reorders via `onReorder` (if given); onto a
 * card in a different column, it restatuses to that card's status. Card
 * contents and any per-card actions are rendered by `renderCard`.
 */
export function EntityBoard<T extends { id: string }>({
  items, columns, statusOf, onRestatus, renderCard, hint = 'Drag a card to change its status', onAddColumn, onReorder,
}: {
  items: T[]
  columns: BoardCol[]
  statusOf: (item: T) => string
  onRestatus: (item: T, status: string) => void
  renderCard: (item: T) => ReactNode
  hint?: string
  onAddColumn?: () => void
  onReorder?: (dragId: string, targetId: string) => void
}) {
  const [dragId, setDragId] = useState<string | null>(null)
  const [overCol, setOverCol] = useState<string | null>(null)

  function dropOnColumn(col: BoardCol) {
    const id = dragId
    setOverCol(null)
    setDragId(null)
    if (!id) return
    const item = items.find(i => i.id === id)
    if (!item) return
    const status = nextStatusForColumn(statusOf(item), col)
    if (status) onRestatus(item, status)
  }

  function dropOnCard(targetId: string) {
    const id = dragId
    setOverCol(null)
    setDragId(null)
    if (!id || id === targetId) return
    const dragItem = items.find(i => i.id === id)
    const targetItem = items.find(i => i.id === targetId)
    if (!dragItem || !targetItem) return
    const targetStatus = statusOf(targetItem)
    if (statusOf(dragItem) === targetStatus) onReorder?.(id, targetId)
    else onRestatus(dragItem, targetStatus)
  }

  return (
    <>
      <div className="pp-toolbar">
        <span className="pp-done-lbl">{hint}</span>
      </div>
      <div className="pp-board-wrap">
        <div className="ab-board">
          {columns.map(col => {
            const colItems = items.filter(i => col.statuses.includes(statusOf(i)))
            return (
              <div
                key={col.key}
                className={`ab-col${overCol === col.key ? ' ab-col-over' : ''}`}
                onDragOver={e => { e.preventDefault(); if (overCol !== col.key) setOverCol(col.key) }}
                onDragLeave={() => setOverCol(c => (c === col.key ? null : c))}
                onDrop={() => dropOnColumn(col)}
              >
                <div className="ab-col-head">
                  <span className="ab-col-dot" style={{ background: col.dot }} />
                  <span className="ab-col-title">{col.label}</span>
                  <span className="ab-col-count">{colItems.length}</span>
                </div>
                {colItems.map(item => (
                  <div
                    key={item.id}
                    className="ab-task-card"
                    draggable
                    onDragStart={() => setDragId(item.id)}
                    onDragEnd={() => { setDragId(null); setOverCol(null) }}
                    onDragOver={e => { e.preventDefault(); e.stopPropagation() }}
                    onDrop={e => { e.preventDefault(); e.stopPropagation(); dropOnCard(item.id) }}
                  >
                    {renderCard(item)}
                  </div>
                ))}
              </div>
            )
          })}
          {onAddColumn && (
            <div className="ab-col ab-col-add">
              <button type="button" className="ab-col-add-btn" onClick={onAddColumn}>+ Add column</button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
