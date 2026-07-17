import { useEffect, useRef, useState } from 'react'
import { StatusBadge, type ToneKind } from './StatusBadge'

/**
 * A `StatusBadge` you can click to change the value inline — no row expansion.
 * Opens a small popover listing `options`; picking one calls `onChange`.
 * Keyboard: Enter/Space opens, Escape closes, arrows move, Enter selects.
 */
export function InlineStatusSelect({
  kind, value, options, onChange, disabled = false, label = 'Change status', onAddNew, colorOf,
}: {
  kind: ToneKind
  value: string
  options: string[]
  onChange: (next: string) => void
  disabled?: boolean
  label?: string
  onAddNew?: () => void
  colorOf?: (key: string) => string | null | undefined
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <span className="pp-inline-status" ref={wrapRef}>
      <button
        type="button"
        className="pp-inline-status-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        disabled={disabled}
        onClick={e => { e.stopPropagation(); setOpen(v => !v) }}
      >
        <StatusBadge kind={kind} value={value} color={colorOf?.(value)} />
      </button>
      {open && (
        <div className="pp-inline-status-menu" role="listbox">
          {options.map(opt => (
            <button
              key={opt}
              type="button"
              role="option"
              aria-selected={opt === value}
              className={`pp-inline-status-item${opt === value ? ' active' : ''}`}
              onClick={e => { e.stopPropagation(); setOpen(false); if (opt !== value) onChange(opt) }}
            >
              <StatusBadge kind={kind} value={opt} color={colorOf?.(opt)} />
            </button>
          ))}
          {onAddNew && (
            <button
              type="button"
              className="pp-inline-status-item pp-inline-status-add"
              onClick={e => { e.stopPropagation(); setOpen(false); onAddNew() }}
            >
              + Add status…
            </button>
          )}
        </div>
      )}
    </span>
  )
}
