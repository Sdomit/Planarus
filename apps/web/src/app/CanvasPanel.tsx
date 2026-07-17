import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from '../api/client'
import './docs-panel.css'

// Excalidraw is heavy (~1MB) and browser-only — lazy-load it, same as DocsPanel.
const CanvasEditor = lazy(() =>
  import('./CanvasEditor').then((m) => ({ default: m.CanvasEditor })),
)

// One canvas per project, reached directly from the Cockpit. The backend lists
// docs ordered by (sort_order, created_at), so docs[0] is deterministically the
// project's primary canvas; create one on first open.
interface CanvasPanelProps { projectId: string; onBack: () => void }

export default function CanvasPanel({ projectId, onBack }: CanvasPanelProps) {
  const [docId, setDocId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setDocId(null); setError(null)
    ;(async () => {
      try {
        const docs = await api.docs.list(projectId, { doc_type: 'canvas' })
        const doc = docs[0] ?? await api.docs.create(projectId, {
          title: 'Canvas', doc_type: 'canvas', editor_format: 'excalidraw',
        })
        if (!cancelled) setDocId(doc.id)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => { cancelled = true }
  }, [projectId])

  if (error) return <p className="dp-state dp-error">{error}</p>
  if (!docId) return <p className="dp-state">Loading canvas…</p>
  return (
    <Suspense fallback={<p className="dp-state">Loading canvas…</p>}>
      <CanvasEditor docId={docId} onBack={onBack} />
    </Suspense>
  )
}
