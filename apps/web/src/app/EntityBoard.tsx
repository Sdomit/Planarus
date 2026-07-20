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
  items, columns, statusOf, onRestatus, renderCard,
  // Was "Drag a card to change its status" — untrue on touch, where drag
  // events never fire and the arrows are the only route.
  hint = 'Drag a card, or use its arrows, to change status',
  onAddColumn, onReorder, labelOf,
}: {
  items: T[]
  columns: BoardCol[]
  statusOf: (item: T) => string
  onRestatus: (item: T, status: string) => void
  renderCard: (item: T) => ReactNode
  hint?: string
  onAddColumn?: () => void
  onReorder?: (dragId: string, targetId: string) => void
  /** Card name, used for the move buttons' aria-labels. */
  labelOf?: (item: T) => string
}) {
  const [dragId, setDragId] = useState<string | null>(null)
  const [overCol, setOverCol] = useState<string | null>(null)

  const columnIndexOf = (item: T) => columns.findIndex(c => c.statuses.includes(statusOf(item)))

  /**
   * Shift a card one column left/right.
   *
   * Dragging is mouse-only — HTML5 drag events never fire on touch — and board
   * cards carry no status control of their own, so without this a card cannot
   * change status on a phone by any route. Doubles as the keyboard path.
   *
   * ponytail: columns only. Reordering WITHIN a column stays drag-only here;
   * the list view has up/down buttons for that. Add it if the board actually
   * gets used for fine-grained ordering on touch.
   */
  function moveByColumn(item: T, delta: -1 | 1) {
    const from = columnIndexOf(item)
    if (from < 0) return
    const to = from + delta
    if (to < 0 || to >= columns.length) return
    const status = nextStatusForColumn(statusOf(item), columns[to])
    if (status) onRestatus(item, status)
  }

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
                {colItems.map(item => {
                  const at = columnIndexOf(item)
                  const name = labelOf?.(item) ?? 'card'
                  return (
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
                      <div className="ab-card-move" onClick={e => e.stopPropagation()}>
                        <button
                          type="button" className="ab-card-move-btn"
                          disabled={at <= 0}
                          aria-label={at > 0 ? `Move ${name} to ${columns[at - 1].label}` : `${name} is in the first column`}
                          onClick={() => moveByColumn(item, -1)}
                        >
                          <span aria-hidden="true">‹</span>
                        </button>
                        <button
                          type="button" className="ab-card-move-btn"
                          disabled={at < 0 || at >= columns.length - 1}
                          aria-label={at >= 0 && at < columns.length - 1 ? `Move ${name} to ${columns[at + 1].label}` : `${name} is in the last column`}
                          onClick={() => moveByColumn(item, 1)}
                        >
                          <span aria-hidden="true">›</span>
                        </button>
                      </div>
                    </div>
                  )
                })}
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
