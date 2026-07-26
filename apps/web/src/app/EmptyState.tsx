import type { ReactNode } from 'react'

/**
 * The illustrated empty state: icon, what this surface is for, and the one
 * action that fills it. Roadmap had this shape inline while Planning and
 * Approvals shipped a bare sentence (#159) — this is that markup extracted, on
 * the existing `.ab-empty` styles, so there is one shape rather than two.
 */
export function EmptyState({ icon, title, hint, action }: {
  icon?: ReactNode
  title: string
  hint: string
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="ab-empty">
      {icon && <div className="ab-empty-art" aria-hidden="true">{icon}</div>}
      <h3>{title}</h3>
      <p>{hint}</p>
      {action && (
        <button type="button" className="btn btn-solid btn-sm" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}
