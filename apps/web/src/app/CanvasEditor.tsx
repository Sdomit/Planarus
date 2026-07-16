import { useCallback, useEffect, useRef, useState } from 'react'
import { Excalidraw, serializeAsJSON } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import { api, type Doc } from '../api/client'
import { StatusBadge } from './StatusBadge'

// Self-host fonts so the canvas works fully offline (no CDN fetch). Vite serves
// apps/web/public/ at '/', so Excalidraw resolves /fonts/<Family>/... locally.
// ponytail: only the Latin families are vendored under public/fonts; the 13MB
// Xiaolai CJK font is not — offline CJK glyphs + auto-resync-on-package-upgrade
// are deferred (see docs/plan/12-local-canvas.md).
declare global {
  interface Window {
    EXCALIDRAW_ASSET_PATH?: string
  }
}
if (typeof window !== 'undefined') window.EXCALIDRAW_ASSET_PATH = '/'

const SAVE_DEBOUNCE_MS = 1500

type SceneChange = Parameters<typeof serializeAsJSON>
type SaveState = 'saved' | 'unsaved' | 'saving' | 'conflict' | 'error'

interface CanvasEditorProps {
  docId: string
  onBack: () => void
}

interface InitialScene {
  elements: SceneChange[0]
  appState: Record<string, unknown>
  files: SceneChange[2]
}

export function CanvasEditor({ docId, onBack }: CanvasEditorProps) {
  const [doc, setDoc] = useState<Doc | null>(null)
  const [scene, setScene] = useState<InitialScene | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [saveError, setSaveError] = useState<string | null>(null)
  const versionRef = useRef(1)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setLoading(true)
    setLoadError(null)
    api.docs
      .get(docId)
      .then((d) => {
        setDoc(d)
        versionRef.current = d.version
        let parsed: Record<string, unknown> = {}
        try {
          parsed = JSON.parse(d.content_json)
        } catch {
          /* start from an empty scene on unparseable content */
        }
        setScene({
          elements: (parsed.elements as SceneChange[0]) ?? [],
          appState: (parsed.appState as Record<string, unknown>) ?? {},
          files: (parsed.files as SceneChange[2]) ?? {},
        })
        setSaveState('saved')
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false))
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [docId])

  const persist = useCallback(async (json: string) => {
    setSaveState('saving')
    setSaveError(null)
    try {
      // markdown_cache stays empty for canvases (text extraction deferred); the
      // API requires content_json + markdown_cache together, so send both.
      const updated = await api.docs.update(docId, {
        version: versionRef.current,
        content_json: json,
        markdown_cache: '',
      })
      versionRef.current = updated.version
      setSaveState('saved')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setSaveState('conflict')
      else {
        setSaveState('error')
        setSaveError(msg)
      }
    }
  }, [docId])

  const onChange = useCallback(
    (elements: SceneChange[0], appState: SceneChange[1], files: SceneChange[2]) => {
      // Excalidraw fires onChange on pointer moves too; debounce the real save.
      setSaveState((s) => (s === 'saving' ? s : 'unsaved'))
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        // ponytail: content_json is capped at 2MB server-side; base64 images
        // pasted inline can exceed it (content-addressed asset store deferred).
        persist(serializeAsJSON(elements, appState, files, 'local'))
      }, SAVE_DEBOUNCE_MS)
    },
    [persist],
  )

  if (loading) return <p className="dp-state">Loading canvas…</p>
  if (loadError) return <p className="dp-state dp-error">{loadError}</p>
  if (!doc || !scene) return <p className="dp-state dp-error">Canvas not found.</p>

  const saveLabel =
    saveState === 'saving' ? 'Saving…' :
    saveState === 'saved' ? 'Saved' :
    saveState === 'unsaved' ? 'Unsaved changes' :
    saveState === 'conflict' ? '⚠ Updated elsewhere — reopen to reload' :
    `Error: ${saveError ?? 'unknown'}`

  return (
    <div className="ab-editor">
      <div
        className="dp-editor-nav"
        style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)' }}
      >
        <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to list">← Back</button>
        <span className="dp-editor-name">{doc.title}</span>
        <StatusBadge kind="docstatus" value={doc.status} />
        <span className={`dp-save-label ${saveState}`} style={{ marginLeft: 'auto' }}>{saveLabel}</span>
      </div>
      <div style={{ height: '78vh', minHeight: 400 }}>
        <Excalidraw
          initialData={{ elements: scene.elements, appState: scene.appState, files: scene.files }}
          onChange={onChange}
        />
      </div>
    </div>
  )
}
