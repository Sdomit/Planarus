import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icon'

/** A kebab (⋮) button that opens a dropdown of actions. Closes on outside
 *  click, Escape, or after an item is chosen. */
export function Menu({ label = 'More actions', children }: { label?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div className="ab-menu" ref={ref}>
      <button type="button" className="ab-menu-btn2" aria-haspopup="menu" aria-expanded={open}
        aria-label={label} onClick={() => setOpen(v => !v)}>
        <Icon name="more" />
      </button>
      {open && (
        <div className="ab-menu-pop" role="menu" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  )
}

export function MenuItem({ onClick, danger = false, children }: {
  onClick: () => void; danger?: boolean; children: ReactNode
}) {
  return (
    <button type="button" role="menuitem" className={`ab-menu-item${danger ? ' danger' : ''}`} onClick={onClick}>
      {children}
    </button>
  )
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <div className="ab-menu-label">{children}</div>
}
