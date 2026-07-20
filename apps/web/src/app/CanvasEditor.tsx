import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Excalidraw, serializeAsJSON, convertToExcalidrawElements } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import { api, type Doc, type Comment } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { usePresence } from './usePresence'
import {
  CARD_KINDS,
  CARD_STYLE,
  KIND_NAME,
  cardLabel,
  readCardRef,
  readReviewPin,
  taskToRef,
  decisionToRef,
  riskToRef,
  milestoneToRef,
  type EntityCardRef,
  type EntityRef,
} from './canvasCards'
import { CANVAS_SHAPES } from './canvasShapes'

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

// Minimal structural view of the bits of the Excalidraw imperative API we use —
// avoids depending on the package's type subpath.
interface CanvasApi {
  getAppState: () => {
    width: number
    height: number
    scrollX: number
    scrollY: number
    zoom: { value: number }
  }
  getSceneElements: () => readonly unknown[]
  updateScene: (scene: { elements: readonly unknown[] }) => void
  scrollToContent: (target?: readonly unknown[], opts?: { fitToContent?: boolean }) => void
  toggleSidebar: (opts: { name: string; tab?: string; force?: boolean }) => boolean
}

// The shape library, seeded into Excalidraw's own library panel. Built once at
// module load: the set is static, so there is nothing to recompute per canvas.
// `created: 0` keeps the order stable (and deterministic) — Excalidraw only uses
// it for sorting, and a real clock would shuffle the groups on every reload.
const SHAPE_LIBRARY = CANVAS_SHAPES.map((shape) => ({
  id: `approvo-${shape.key}`,
  status: 'published' as const,
  created: 0,
  name: `${shape.group} · ${shape.name}`,
  elements: convertToExcalidrawElements(
    shape.elements as Parameters<typeof convertToExcalidrawElements>[0],
  ),
}))

interface CanvasEditorProps {
  docId: string
  onBack: () => void
}

interface InitialScene {
  elements: SceneChange[0]
  appState: Record<string, unknown>
  files: SceneChange[2]
}

// A cheap signature of the *content* (drawing), ignoring volatile appState like
// selection/cursor/view. Excalidraw bumps an element's `version` on every edit
// and fires onChange on ambient appState ticks too — without this guard the
// canvas would autosave (and inflate Doc.version) endlessly while just open.
function contentSig(
  elements: ReadonlyArray<{ id?: string; version?: number; isDeleted?: boolean }>,
  files: Record<string, unknown> | undefined,
): string {
  const els = elements.filter((e) => !e.isDeleted).map((e) => `${e.id}:${e.version ?? 0}`).join(',')
  return `${els}|${files ? Object.keys(files).sort().join(',') : ''}`
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
  const lastContentSig = useRef('')

  // Entity-binding cards (Phase 13). Cards are ordinary Excalidraw elements whose
  // customData carries { approvoEntity: { kind, id } } — the binding lives in the
  // canonical content_json, so it survives autosave/reload with no backend change.
  const apiRef = useRef<CanvasApi | null>(null)
  const projectIdRef = useRef('')
  const entitiesLoaded = useRef(false)
  const [entities, setEntities] = useState<EntityRef[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selectedCard, setSelectedCard] = useState<EntityCardRef | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const lastSelKey = useRef('')

  // Review comments (Phase 13c). A canvas is a Doc, so comments attach via the
  // existing polymorphic Comment API (entity_type='doc'). A "review pin" is a
  // canvas marker element whose customData links it to one of those comments.
  const [showComments, setShowComments] = useState(false)
  const [comments, setComments] = useState<Comment[]>([])
  const commentsLoaded = useRef(false)
  const [commentBody, setCommentBody] = useState('')

  // P11.2 soft-lock: dormant in local mode (the presence surface 404s); in team
  // mode the first active editor holds the lock and everyone else goes view-only.
  const { lockedByOther, editorName } = usePresence(docId, true)

  const entityMap = useMemo(() => new Map(entities.map((e) => [e.id, e])), [entities])
  const groups = useMemo(() => {
    const g: Record<string, EntityRef[]> = { task: [], decision: [], risk: [], milestone: [] }
    for (const e of entities) g[e.kind].push(e)
    return g
  }, [entities])

  const loadEntities = useCallback(async () => {
    const pid = projectIdRef.current
    if (!pid || entitiesLoaded.current) return
    entitiesLoaded.current = true
    try {
      const [t, d, r, m] = await Promise.all([
        api.tasks.list(pid),
        api.decisions.list(pid),
        api.risks.list(pid),
        api.milestones.list(pid),
      ])
      setEntities([
        ...t.map(taskToRef),
        ...d.map(decisionToRef),
        ...r.map(riskToRef),
        ...m.map(milestoneToRef),
      ])
    } catch {
      entitiesLoaded.current = false // allow a retry on next open
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    setLoadError(null)
    api.docs
      .get(docId)
      .then((d) => {
        setDoc(d)
        versionRef.current = d.version
        projectIdRef.current = d.project_id
        let parsed: Record<string, unknown> = {}
        try {
          parsed = JSON.parse(d.content_json)
        } catch {
          /* start from an empty scene on unparseable content */
        }
        const els = (parsed.elements as { customData?: unknown }[]) ?? []
        setScene({
          elements: els as unknown as SceneChange[0],
          appState: (parsed.appState as Record<string, unknown>) ?? {},
          files: (parsed.files as SceneChange[2]) ?? {},
        })
        // Seed the save-guard from the loaded scene so reopening an unchanged
        // canvas doesn't immediately re-save.
        lastContentSig.current = contentSig(
          els as unknown as Parameters<typeof contentSig>[0],
          parsed.files as Record<string, unknown> | undefined,
        )
        // Pre-fetch entities so selecting an existing card can show live status.
        if (els.some((el) => readCardRef(el.customData))) loadEntities()
        setSaveState('saved')
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false))
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [docId, loadEntities])

  const persist = useCallback(async (json: string, sig: string) => {
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
      lastContentSig.current = sig
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
      // Track which bound card (if exactly one) is selected, for the header chip.
      const sel = appState.selectedElementIds as Record<string, unknown>
      const picked = elements.filter((el) => sel[el.id] && !el.isDeleted)
      const ref = picked.length === 1 ? readCardRef(picked[0].customData) : null
      const key = ref ? `${ref.kind}:${ref.id}` : ''
      if (key !== lastSelKey.current) {
        lastSelKey.current = key
        setSelectedCard(ref)
        setDetailsOpen(false)
      }

      // Debounce; the tick skips the save when only volatile appState changed
      // (selection/cursor/view) so an idle-but-open canvas doesn't churn saves.
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        const sig = contentSig(elements, files as Record<string, unknown>)
        if (sig === lastContentSig.current) return
        // ponytail: content_json is capped at 2MB server-side; base64 images
        // pasted inline can exceed it (content-addressed asset store deferred).
        persist(serializeAsJSON(elements, appState, files, 'local'), sig)
      }, SAVE_DEBOUNCE_MS)
    },
    [persist],
  )

  const openPicker = useCallback(() => {
    loadEntities()
    setPickerOpen((o) => !o)
  }, [loadEntities])

  const insertCard = useCallback((ref: EntityRef) => {
    const canvas = apiRef.current
    if (!canvas) return
    const st = canvas.getAppState()
    const zoom = st.zoom.value || 1
    // scene coordinate at the viewport centre: screen = (scene + scroll) * zoom.
    const cx = st.width / (2 * zoom) - st.scrollX
    const cy = st.height / (2 * zoom) - st.scrollY
    const style = CARD_STYLE[ref.kind]
    const skeleton = {
      type: 'rectangle',
      x: cx - 120,
      y: cy - 48,
      width: 240,
      height: 96,
      backgroundColor: style.bg,
      strokeColor: style.stroke,
      fillStyle: 'solid',
      roundness: { type: 3 },
      customData: { approvoEntity: { kind: ref.kind, id: ref.id } },
      label: { text: cardLabel(ref), fontSize: 16, strokeColor: '#1e1e1e' },
    }
    const created = convertToExcalidrawElements([
      skeleton,
    ] as Parameters<typeof convertToExcalidrawElements>[0])
    canvas.updateScene({ elements: [...canvas.getSceneElements(), ...created] })
    setPickerOpen(false)
  }, [])

  // Sticky note (Miro/FigJam style): a plain freeform Excalidraw rectangle with
  // a text label, no entity binding — just a preset the toolbar lacks. Recolor,
  // resize, and edit text with Excalidraw's own controls (double-click to type).
  const addNote = useCallback(() => {
    const canvas = apiRef.current
    if (!canvas) return
    const st = canvas.getAppState()
    const zoom = st.zoom.value || 1
    const cx = st.width / (2 * zoom) - st.scrollX
    const cy = st.height / (2 * zoom) - st.scrollY
    const skeleton = {
      type: 'rectangle',
      x: cx - 90,
      y: cy - 90,
      width: 180,
      height: 180,
      backgroundColor: '#ffec99', // sticky yellow
      strokeColor: '#f08c00',
      fillStyle: 'solid',
      roundness: null, // square corners, like a real sticky
      label: { text: 'New note', fontSize: 20, strokeColor: '#1e1e1e' },
    }
    const created = convertToExcalidrawElements([skeleton] as Parameters<typeof convertToExcalidrawElements>[0])
    canvas.updateScene({ elements: [...canvas.getSceneElements(), ...created] })
  }, [])

  // The seeded shapes live in Excalidraw's library panel; this just toggles it,
  // so there is no second shape palette to build or keep in sync with the
  // toolbar. Note the naming: the *sidebar* is 'default' and 'library' is a tab
  // inside it (DEFAULT_SIDEBAR in the package's constants). Passing
  // name:'library' matches no sidebar and is silently ignored — as is writing
  // openSidebar through updateScene's appState. Both fail without an error.
  const openShapes = useCallback(() => {
    apiRef.current?.toggleSidebar({ name: 'default', tab: 'library' })
  }, [])

  const loadComments = useCallback(async () => {
    if (commentsLoaded.current) return
    commentsLoaded.current = true
    try {
      setComments(await api.comments.list(projectIdRef.current, { entity_type: 'doc', entity_id: docId }))
    } catch {
      commentsLoaded.current = false // allow a retry
    }
  }, [docId])

  const addComment = useCallback(async (body: string) => {
    const text = body.trim()
    if (!text) return
    const c = await api.comments.create(projectIdRef.current, { entity_type: 'doc', entity_id: docId, body: text })
    setComments((prev) => [...prev, c])
    setCommentBody('')
  }, [docId])

  const addPin = useCallback(async () => {
    const canvas = apiRef.current
    if (!canvas) return
    const note = window.prompt('Review pin note')
    if (note == null || !note.trim()) return
    const c = await api.comments.create(projectIdRef.current, { entity_type: 'doc', entity_id: docId, body: note.trim() })
    setComments((prev) => [...prev, c])
    const st = canvas.getAppState()
    const zoom = st.zoom.value || 1
    const cx = st.width / (2 * zoom) - st.scrollX
    const cy = st.height / (2 * zoom) - st.scrollY
    const num = canvas.getSceneElements().filter((el) => readReviewPin((el as { customData?: unknown }).customData)).length + 1
    const skeleton = {
      type: 'ellipse',
      x: cx - 16,
      y: cy - 16,
      width: 32,
      height: 32,
      backgroundColor: '#ffe066',
      strokeColor: '#e8590c',
      fillStyle: 'solid',
      customData: { reviewPin: { commentId: c.id } },
      label: { text: String(num), fontSize: 14, strokeColor: '#1e1e1e' },
    }
    const created = convertToExcalidrawElements([skeleton] as Parameters<typeof convertToExcalidrawElements>[0])
    canvas.updateScene({ elements: [...canvas.getSceneElements(), ...created] })
    setShowComments(true)
  }, [docId])

  const scrollToPin = useCallback((commentId: string) => {
    const canvas = apiRef.current
    if (!canvas) return
    const marker = canvas.getSceneElements().find((el) => readReviewPin((el as { customData?: unknown }).customData) === commentId)
    if (marker) canvas.scrollToContent([marker], { fitToContent: false })
  }, [])

  if (loading) return <p className="dp-state">Loading canvas…</p>
  if (loadError) return <p className="dp-state dp-error">{loadError}</p>
  if (!doc || !scene) return <p className="dp-state dp-error">Canvas not found.</p>

  const saveLabel =
    saveState === 'saving' ? 'Saving…' :
    saveState === 'saved' ? 'Saved' :
    saveState === 'unsaved' ? 'Unsaved changes' :
    saveState === 'conflict' ? '⚠ Updated elsewhere — reopen to reload' :
    `Error: ${saveError ?? 'unknown'}`

  const live = selectedCard ? entityMap.get(selectedCard.id) : undefined
  const pinIds = new Set(
    (apiRef.current?.getSceneElements() ?? [])
      .map((el) => readReviewPin((el as { customData?: unknown }).customData))
      .filter((id): id is string => !!id),
  )
  const panelStyle: CSSProperties = {
    position: 'absolute',
    top: 'calc(100% + 4px)',
    zIndex: 30,
    background: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    boxShadow: 'var(--shadow-lg)',
    padding: 'var(--space-2)',
  }

  return (
    <div className="ab-editor">
      <div
        className="dp-editor-nav"
        style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)', position: 'relative' }}
      >
        <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to list">← Back</button>
        <span className="dp-editor-name">{doc.title}</span>
        <StatusBadge kind="docstatus" value={doc.status} />
        {lockedByOther && (
          <span
            className="badge badge-warning badge-sm"
            title="Someone else holds the edit lock; your canvas is read-only until they leave"
          >
            🔒 {editorName} is editing — read-only
          </span>
        )}
        <button className="btn btn-outline btn-sm" onClick={openPicker} title="Insert a card bound to a project entity">
          ＋ Card
        </button>
        <button className="btn btn-outline btn-sm" onClick={addNote} title="Drop a sticky note (recolor & edit with Excalidraw's controls)">
          🟨 Note
        </button>
        <button className="btn btn-outline btn-sm" onClick={openShapes} title={`Open the shape library — ${CANVAS_SHAPES.length} flowchart, planning and annotation shapes to drag onto the canvas`}>
          ⬡ Shapes
        </button>
        <button className="btn btn-outline btn-sm" onClick={addPin} title="Drop a review pin on the canvas, bound to a comment">
          📍 Pin
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => { setShowComments((o) => !o); loadComments() }} title="Review comments">
          💬 Comments{comments.length ? ` (${comments.length})` : ''}
        </button>
        {selectedCard && (
          <span className="badge badge-neutral badge-sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)', maxWidth: 360 }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              🔗 {live
                ? `${KIND_NAME[live.kind]}: ${live.title} · ${live.meta ? `${live.status} · ${live.meta}` : live.status}`
                : `${KIND_NAME[selectedCard.kind]} · unavailable`}
            </span>
            {live && (
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => setDetailsOpen((o) => !o)}>
                {detailsOpen ? 'Hide' : 'Details'}
              </button>
            )}
          </span>
        )}
        <span className={`dp-save-label ${saveState}`} style={{ marginLeft: 'auto' }}>{saveLabel}</span>

        {pickerOpen && (
          <div style={{ ...panelStyle, left: 'var(--space-4)', width: 300, maxHeight: 380, overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 var(--space-2) var(--space-2)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Insert entity card</span>
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => setPickerOpen(false)}>✕</button>
            </div>
            {entities.length === 0 ? (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', padding: 'var(--space-2)' }}>
                {entitiesLoaded.current ? 'No tasks, decisions, risks, or milestones in this project yet.' : 'Loading…'}
              </div>
            ) : (
              CARD_KINDS.map((kind) => (
                <div key={kind}>
                  <div style={{ fontSize: 'var(--text-2xs, 10px)', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-tertiary)', padding: 'var(--space-2) var(--space-2) var(--space-1)' }}>
                    {KIND_NAME[kind]}s
                  </div>
                  {groups[kind].length === 0 ? (
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', padding: '0 var(--space-2) var(--space-1)' }}>none</div>
                  ) : (
                    groups[kind].map((e) => (
                      <button
                        key={e.id}
                        type="button"
                        onClick={() => insertCard(e)}
                        style={{ display: 'block', width: '100%', textAlign: 'left', padding: 'var(--space-1) var(--space-2)', border: 'none', background: 'transparent', color: 'var(--text-primary)', fontSize: 'var(--text-sm)', cursor: 'pointer', borderRadius: 'var(--radius-sm)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      >
                        {e.title} <span style={{ color: 'var(--text-tertiary)' }}>· {e.status}</span>
                      </button>
                    ))
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {detailsOpen && live && (
          <div style={{ ...panelStyle, right: 'var(--space-4)', width: 320 }}>
            <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-tertiary)' }}>
              {KIND_NAME[live.kind]}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)', margin: 'var(--space-1) 0' }}>{live.title}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              status: {live.status}{live.meta ? ` · ${live.meta}` : ''}
            </div>
            {live.detail && (
              <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', margin: 'var(--space-2) 0 0', whiteSpace: 'pre-wrap', maxHeight: 160, overflowY: 'auto' }}>
                {live.detail}
              </p>
            )}
          </div>
        )}
      </div>
      <div style={{ position: 'relative', height: '78vh', minHeight: 400 }}>
        <Excalidraw
          excalidrawAPI={(inst) => { apiRef.current = inst as unknown as CanvasApi }}
          initialData={{ elements: scene.elements, appState: scene.appState, files: scene.files, libraryItems: SHAPE_LIBRARY }}
          onChange={onChange}
          viewModeEnabled={lockedByOther}
        />
        {showComments && (
          <div
            style={{
              position: 'absolute', top: 0, right: 0, width: 300, height: '100%', zIndex: 5,
              background: 'var(--bg-surface)', borderLeft: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-lg)', display: 'flex', flexDirection: 'column',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 'var(--space-3)', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Comments</span>
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => setShowComments(false)}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {comments.length === 0 ? (
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', padding: 'var(--space-3)' }}>
                  {commentsLoaded.current ? 'No comments yet. Add one below, or drop a 📍 pin.' : 'Loading…'}
                </p>
              ) : (
                comments.map((c) => {
                  const pinned = pinIds.has(c.id)
                  return (
                    <div
                      key={c.id}
                      onClick={pinned ? () => scrollToPin(c.id) : undefined}
                      title={pinned ? 'Jump to pin on canvas' : undefined}
                      style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--border-subtle)', cursor: pinned ? 'pointer' : 'default' }}
                    >
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                        {pinned && '📍 '}{c.body}
                      </div>
                      <div style={{ fontSize: 'var(--text-2xs, 10px)', color: 'var(--text-tertiary)', marginTop: 2 }}>
                        {c.author_type} · {c.created_at.slice(0, 10)}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
            <form
              onSubmit={(e) => { e.preventDefault(); void addComment(commentBody) }}
              style={{ display: 'flex', gap: 'var(--space-2)', padding: 'var(--space-2)', borderTop: '1px solid var(--border-subtle)' }}
            >
              <input className="input" style={{ flex: 1 }} placeholder="Add a comment…" value={commentBody} onChange={(e) => setCommentBody(e.target.value)} />
              <button type="submit" className="btn btn-solid btn-sm" disabled={!commentBody.trim()}>Post</button>
            </form>
          </div>
        )}
      </div>
    </div>
  )
}
