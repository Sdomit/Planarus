import { useState } from 'react'
import { Icon } from './Icon'

/**
 * Inline row controls: a drag handle, an edit (pencil) button, and a delete
 * (trash) button with a two-step inline confirm. All optional — pass only what
 * a given row supports.
 */
export function RowActions({
  onEdit, onDelete, dragHandle = false, title = '',
}: {
  onEdit?: () => void
  onDelete?: () => void
  dragHandle?: boolean
  title?: string
}) {
  const [confirming, setConfirming] = useState(false)
  return (
    <span className="pp-row-actions" onClick={e => e.stopPropagation()}>
      {dragHandle && (
        <span className="pp-drag-handle" aria-hidden="true" title="Drag to reorder">⠿</span>
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
