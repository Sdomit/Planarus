import { useEffect, useRef, useState } from 'react'
import { api, StatusCategory, StatusOption } from '../api/client'
import { StatusBadge, type ToneKind } from './StatusBadge'

const DEFAULT_COLOR = '#8b5cf6'

// What a column means, in the user's words. The roadmap %, the due-date
// reminders and the agent brief all read this — a column named "Shipped" only
// counts as finished once it is marked Done here.
const CATEGORIES: { value: StatusCategory; label: string }[] = [
  { value: 'open', label: 'In progress' },
  { value: 'done', label: 'Done' },
  { value: 'canceled', label: 'Canceled' },
]

/**
 * Modal for managing a project's custom statuses for one entity type: rename,
 * recolor, reorder (up/down), delete, and add. Built-in statuses are shown
 * read-only — only the project's own custom options can be edited. Every
 * mutation refreshes the parent via `onChanged`.
 */
export function StatusManager({
  projectId, entityType, kind, options, onClose, onChanged,
}: {
  projectId: string
  entityType: string
  kind: ToneKind
  options: StatusOption[]
  onClose: () => void
  onChanged: () => Promise<void> | void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    try { d.showModal?.() } catch { /* environments without modal support */ }
    if (!d.open) d.setAttribute('open', '')  // fallback so the dialog is visible
  }, [])
  const close = () => { const d = ref.current; if (d?.close) d.close(); else onClose() }

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newLabel, setNewLabel] = useState('')
  const [newColor, setNewColor] = useState(DEFAULT_COLOR)
  const [newCategory, setNewCategory] = useState<StatusCategory>('open')

  const builtins = options.filter(o => o.builtin)
  const custom = options.filter(o => !o.builtin && o.id)

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError(null)
    try {
      await fn()
      await onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const rename = (o: StatusOption, label: string) => {
    const t = label.trim()
    if (!t || t === o.label) return
    void run(() => api.statusOptions.update(o.id!, { label: t }))
  }
  const recolor = (o: StatusOption, color: string) =>
    void run(() => api.statusOptions.update(o.id!, { color }))
  const recategorize = (o: StatusOption, category: StatusCategory) =>
    void run(() => api.statusOptions.update(o.id!, { category }))
  const remove = (o: StatusOption) => void run(() => api.statusOptions.remove(o.id!))

  const move = (index: number, delta: number) => {
    const next = index + delta
    if (next < 0 || next >= custom.length) return
    const ids = custom.map(o => o.id!)
    ;[ids[index], ids[next]] = [ids[next], ids[index]]
    void run(() => api.statusOptions.reorder(projectId, entityType, ids))
  }

  const add = () => {
    const t = newLabel.trim()
    if (!t) return
    void run(async () => {
      await api.statusOptions.create(projectId, {
        entity_type: entityType, label: t, color: newColor, category: newCategory,
      })
      setNewLabel('')
      setNewCategory('open')
    })
  }

  return (
    <dialog
      ref={ref}
      className="pp-dialog"
      onClose={onClose}
      onClick={e => { if (e.target === ref.current) close() }}
    >
      <div className="pp-dialog-head">
        <span className="pp-dialog-title">Manage statuses</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={close} aria-label="Close">✕</button>
      </div>

      <div className="pp-task-details sm-body">
        {error && <p className="sm-error" role="alert">{error}</p>}

        <p className="pp-section-lbl">Built-in</p>
        <ul className="sm-list">
          {builtins.map(o => (
            <li key={o.key} className="sm-row sm-row-builtin">
              <StatusBadge kind={kind} value={o.key} />
              <span className="sm-tag">built-in</span>
            </li>
          ))}
        </ul>

        <p className="pp-section-lbl">Custom</p>
        {custom.length === 0 ? (
          <p className="sm-empty">No custom statuses yet. Add one below.</p>
        ) : (
          <ul className="sm-list">
            {custom.map((o, i) => (
              <li key={o.id} className="sm-row">
                <input
                  type="color" className="sm-swatch" aria-label={`Color for ${o.label}`}
                  value={o.color ?? DEFAULT_COLOR} disabled={busy}
                  onChange={e => recolor(o, e.target.value)}
                />
                <input
                  className="input input-sm sm-label" aria-label={`Rename ${o.label}`}
                  defaultValue={o.label} key={o.label} disabled={busy}
                  onBlur={e => rename(o, e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur() }
                  }}
                />
                <select
                  className="input input-sm sm-category" aria-label={`Meaning of ${o.label}`}
                  value={o.category} disabled={busy}
                  onChange={e => recategorize(o, e.target.value as StatusCategory)}
                >
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <div className="sm-actions">
                  <button type="button" className="sm-icon" aria-label={`Move ${o.label} up`}
                    disabled={busy || i === 0} onClick={() => move(i, -1)}>↑</button>
                  <button type="button" className="sm-icon" aria-label={`Move ${o.label} down`}
                    disabled={busy || i === custom.length - 1} onClick={() => move(i, 1)}>↓</button>
                  <button type="button" className="sm-icon sm-icon-danger" aria-label={`Delete ${o.label}`}
                    disabled={busy} onClick={() => remove(o)}>✕</button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <form
          className="sm-add"
          onSubmit={e => { e.preventDefault(); add() }}
        >
          <input
            type="color" className="sm-swatch" aria-label="New status color"
            value={newColor} onChange={e => setNewColor(e.target.value)} disabled={busy}
          />
          <input
            className="input input-sm sm-label" placeholder="New status name" aria-label="New status name"
            value={newLabel} onChange={e => setNewLabel(e.target.value)} disabled={busy}
          />
          <select
            className="input input-sm sm-category" aria-label="New status meaning"
            value={newCategory} onChange={e => setNewCategory(e.target.value as StatusCategory)}
            disabled={busy}
          >
            {CATEGORIES.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <button type="submit" className="btn btn-solid btn-sm" disabled={busy || !newLabel.trim()}>Add</button>
        </form>
      </div>
    </dialog>
  )
}
