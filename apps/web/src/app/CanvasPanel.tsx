import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api, type DocSummary } from '../api/client'
import './docs-panel.css'

// Excalidraw is heavy (~1MB) and browser-only — lazy-load it, same as DocsPanel.
const CanvasEditor = lazy(() =>
  import('./CanvasEditor').then((m) => ({ default: m.CanvasEditor })),
)

// Many canvases per project: each is its own `Doc` (doc_type='canvas') with its
// own content_json, listed as a tab. Add / rename / delete map onto the docs
// API — no hard-delete route exists, so "delete" archives (archived_at), which
// the default list already hides. The editor is keyed by canvas id so switching
// tabs remounts it: Excalidraw only reads initialData once, so without the key a
// tab switch would show the previous canvas's content.
interface CanvasPanelProps { projectId: string; onBack: () => void }

export default function CanvasPanel({ projectId, onBack }: CanvasPanelProps) {
  const [canvases, setCanvases] = useState<DocSummary[] | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const listCanvases = useCallback(
    () => api.docs.list(projectId, { doc_type: 'canvas' }),
    [projectId],
  )

  useEffect(() => {
    let cancelled = false
    setCanvases(null); setActiveId(null); setError(null)
    ;(async () => {
      try {
        let docs = await listCanvases()
        if (docs.length === 0) {
          await api.docs.create(projectId, {
            title: 'Canvas 1', doc_type: 'canvas', editor_format: 'excalidraw',
          })
          docs = await listCanvases()
        }
        if (!cancelled) { setCanvases(docs); setActiveId(docs[0]?.id ?? null) }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => { cancelled = true }
  }, [projectId, listCanvases])

  const addCanvas = async () => {
    setBusy(true); setError(null)
    try {
      const created = await api.docs.create(projectId, {
        title: `Canvas ${(canvases?.length ?? 0) + 1}`,
        doc_type: 'canvas', editor_format: 'excalidraw',
      })
      setCanvases(await listCanvases())
      setActiveId(created.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  const renameCanvas = async (d: DocSummary) => {
    const title = window.prompt('Rename canvas', d.title)?.trim()
    if (!title || title === d.title) return
    setBusy(true); setError(null)
    try {
      // The active canvas autosaves and bumps its version, so fetch the current
      // one before PATCHing. ponytail: a tiny race remains if an autosave lands
      // between the get and the update — it surfaces as a 409 the user can retry.
      const fresh = await api.docs.get(d.id)
      await api.docs.update(d.id, { version: fresh.version, title })
      setCanvases(await listCanvases())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  const deleteCanvas = async (d: DocSummary) => {
    if (!window.confirm(`Delete canvas "${d.title}"? This permanently deletes it and its comments — you can't undo this.`)) return
    setBusy(true); setError(null)
    try {
      await api.docs.remove(d.id)
      const docs = await listCanvases()
      setCanvases(docs)
      setActiveId((cur) => (cur === d.id ? docs[0]?.id ?? null : cur))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  if (error) return <p className="dp-state dp-error">{error}</p>
  if (canvases === null) return <p className="dp-state">Loading canvas…</p>

  const active = canvases.find((d) => d.id === activeId) ?? null

  return (
    <div className="ab-editor" style={{ display: 'flex', flexDirection: 'column' }}>
      <div
        role="group"
        aria-label="Canvases"
        style={{
          display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'nowrap', overflowX: 'auto',
          padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        {canvases.map((d) => {
          const isActive = d.id === activeId
          return (
            <span
              key={d.id}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 2, whiteSpace: 'nowrap',
                borderRadius: 'var(--radius-md)',
                background: isActive ? 'var(--accent-muted)' : 'transparent',
              }}
            >
              <button
                type="button"
                aria-pressed={isActive}
                onClick={() => setActiveId(d.id)}
                onDoubleClick={() => renameCanvas(d)}
                title={isActive ? 'Double-click to rename' : d.title}
                style={{
                  border: 'none', background: 'transparent', cursor: 'pointer',
                  padding: 'var(--space-1) var(--space-3)', borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--text-sm)', fontWeight: isActive ? 600 : 500,
                  color: isActive ? 'var(--text-accent)' : 'var(--text-secondary)',
                }}
              >
                {d.title}
              </button>
              {isActive && (
                <>
                  <button type="button" className="btn btn-ghost btn-xs" title="Rename canvas"
                    disabled={busy} onClick={() => renameCanvas(d)}>✎</button>
                  <button type="button" className="btn btn-ghost btn-xs" title="Delete canvas"
                    disabled={busy} onClick={() => deleteCanvas(d)} style={{ marginRight: 'var(--space-1)' }}>✕</button>
                </>
              )}
            </span>
          )
        })}
        <button type="button" className="btn btn-outline btn-sm" onClick={addCanvas}
          disabled={busy} title="New canvas" style={{ marginLeft: 4, flexShrink: 0 }}>
          ＋ New
        </button>
      </div>

      {active ? (
        <Suspense fallback={<p className="dp-state">Loading canvas…</p>}>
          {/* key remounts the editor per canvas (and after a version bump from
              rename/delete) so each tab shows its own content, not the last one's. */}
          <CanvasEditor key={`${active.id}:${active.version}`} docId={active.id} onBack={onBack} />
        </Suspense>
      ) : (
        <p className="dp-state">No canvases yet. Use ＋ New to create one.</p>
      )}
    </div>
  )
}
