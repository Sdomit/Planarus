import { useCallback, useEffect, useState } from 'react'
import { api, type FsListing } from '../api/client'
import { Icon } from './Icon'

// Phase 12d: browse the machine the API runs on and pick a folder, instead of
// hand-typing an absolute path. Server lists directory names only, local mode
// only. Repo roots get a badge so the target of "point this at a repo" is
// obvious at a glance.
export default function FolderPicker({ title, onSelect, onClose }: {
  title?: string
  onSelect: (path: string) => void
  onClose: () => void
}) {
  const [listing, setListing] = useState<FsListing | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async (path?: string) => {
    setLoading(true)
    setErr(null)
    try {
      setListing(await api.fs.dirs(path))
    } catch (e) {
      // 409 carries the "local mode only / disabled" explanation verbatim.
      setErr(e instanceof Error ? e.message : 'Could not browse folders.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="modal-header">
          <h2 className="modal-title">{title ?? 'Choose a folder'}</h2>
          <button className="modal-close" type="button" aria-label="Close" onClick={onClose}>
            <Icon name="x" className="ic-18" />
          </button>
        </div>
        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {listing && listing.roots.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {listing.roots.map((root) => (
                <button key={root} type="button" className="btn btn-ghost btn-sm" onClick={() => void load(root)}>
                  <code style={{ fontSize: 'var(--text-xs)' }}>{root}</code>
                </button>
              ))}
            </div>
          )}
          {listing && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={listing.parent == null || loading}
                onClick={() => listing.parent && void load(listing.parent)}
                title="Up one level"
              >
                ↑ Up
              </button>
              <code style={{ fontSize: 'var(--text-sm)', overflowWrap: 'anywhere' }}>{listing.path}</code>
              {listing.is_git && <span className="sbadge sbadge--success"><span className="sdot" />git repo</span>}
            </div>
          )}
          {err && <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--status-danger-fg)' }}>{err}</p>}
          {listing?.message && !err && (
            <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--status-warning-fg)' }}>{listing.message}</p>
          )}
          <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid var(--border-default, #ddd)', borderRadius: 8 }}>
            {loading && <div style={{ padding: 'var(--space-4)' }}><span className="spinner spinner-sm" /> Loading…</div>}
            {!loading && listing && listing.dirs.length === 0 && (
              <p style={{ margin: 0, padding: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>
                No subfolders.
              </p>
            )}
            {!loading && listing?.dirs.map((d) => (
              <button
                key={d.path}
                type="button"
                onClick={() => void load(d.path)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                  padding: '6px 12px', border: 'none', background: 'transparent',
                  cursor: 'pointer', textAlign: 'left', color: 'var(--text-primary)',
                  fontSize: 'var(--text-sm)',
                }}
              >
                <Icon name="folder" className="ic-14" />
                <span style={{ overflowWrap: 'anywhere' }}>{d.name}</span>
                {d.is_git && <span className="sbadge sbadge--success" style={{ marginLeft: 'auto' }}><span className="sdot" />git</span>}
              </button>
            ))}
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
          <button
            type="button"
            className="btn btn-solid btn-sm"
            disabled={!listing || loading}
            onClick={() => listing && onSelect(listing.path)}
          >
            Use this folder
          </button>
        </div>
      </div>
    </div>
  )
}
