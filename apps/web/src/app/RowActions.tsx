import { useState } from 'react'
import { Icon } from './Icon'

/**
 * Inline row controls: a drag handle, move up/down buttons, an edit (pencil)
 * button, and a delete (trash) button with a two-step inline confirm. All
 * optional — pass only what a given row supports.
 *
 * onMoveUp/onMoveDown exist because dragging is mouse-only: HTML5 drag events
 * never fire on iOS or Android, so without these a list cannot be reordered on
 * a touch device at all. They double as the keyboard path.
 */
export function RowActions({
  onEdit, onDelete, onMoveUp, onMoveDown, dragHandle = false, title = '',
}: {
  onEdit?: () => void
  onDelete?: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
  dragHandle?: boolean
  title?: string
}) {
  const [confirming, setConfirming] = useState(false)
  return (
    <span className="pp-row-actions" onClick={e => e.stopPropagation()}>
      {dragHandle && (
        <span className="pp-drag-handle" aria-hidden="true" title="Drag to reorder">⠿</span>
      )}
      {onMoveUp && (
        <button type="button" className="pp-row-act" aria-label={`Move ${title} up`.trim()} onClick={onMoveUp}>
          <span aria-hidden="true">↑</span>
        </button>
      )}
      {onMoveDown && (
        <button type="button" className="pp-row-act" aria-label={`Move ${title} down`.trim()} onClick={onMoveDown}>
          <span aria-hidden="true">↓</span>
        </button>
      )}
      {onEdit && (
        <button type="button" className="pp-row-act" aria-label={`Edit ${title}`.trim()} onClick={onEdit}>
          <Icon name="edit" className="ic-14" />
        </button>
      )}
      {onDelete && (
        confirming ? (
          <span className="pp-confirm">
            <button type="button" className="pp-row-act pp-row-act-danger" onClick={() => { setConfirming(false); onDelete() }}>
              Delete
            </button>
            <button type="button" className="pp-row-act" onClick={() => setConfirming(false)}>Cancel</button>
          </span>
        ) : (
          <button type="button" className="pp-row-act pp-row-act-danger" aria-label={`Delete ${title}`.trim()} onClick={() => setConfirming(true)}>
            <Icon name="trash" className="ic-14" />
          </button>
        )
      )}
    </span>
  )
}
