import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import { TaskList, TaskItem } from '@tiptap/extension-list'
import Image from '@tiptap/extension-image'
import { TextStyle } from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import { MarkdownSerializer } from 'prosemirror-markdown'
import { api, type Doc, type DocSummary } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { usePresence } from './usePresence'
import { agoLabel } from './date'
import { isAllowedImageSrc, isAllowedLink, markdownTitle, markdownUrl } from './uri-policy'
import './docs-panel.css'

// Excalidraw is heavy (~1MB) and pulls in browser-only modules that crash under
// jsdom at import time — lazy-load it so it's fetched only when a canvas opens.
const CanvasEditor = lazy(() =>
  import('./CanvasEditor').then((m) => ({ default: m.CanvasEditor })),
)

// ---------------------------------------------------------------------------
// ProseMirror → Markdown serializer (Tiptap camelCase node/mark names)
// ---------------------------------------------------------------------------

const _docSerializer = new MarkdownSerializer(
  {
    doc(state, node) { state.renderContent(node) },
    paragraph(state, node) { state.renderInline(node); state.closeBlock(node) },
    text(state, node) { state.text(node.text ?? '') },
    heading(state, node) {
      state.write(state.repeat('#', node.attrs.level as number) + ' ')
      state.renderInline(node); state.closeBlock(node)
    },
    blockquote(state, node) { state.wrapBlock('> ', null, node, () => state.renderContent(node)) },
    bulletList(state, node) { state.renderList(node, '  ', () => '* ') },
    orderedList(state, node) {
      const start = (node.attrs.start as number) || 1
      state.renderList(node, '  ', (i: number) => `${start + i}. `)
    },
    listItem(state, node) { state.renderContent(node) },
    // GFM task list: "- [ ] item" / "- [x] item". The checkbox state lives on
    // the item, so taskList supplies the "- " bullet and taskItem the "[x] ".
    taskList(state, node) { state.renderList(node, '  ', () => '- ') },
    taskItem(state, node) {
      state.write(`[${node.attrs.checked ? 'x' : ' '}] `)
      state.renderContent(node)
    },
    codeBlock(state, node) {
      state.write('```' + ((node.attrs.language as string) || '') + '\n')
      state.text(node.textContent, false); state.ensureNewLine()
      state.write('```'); state.closeBlock(node)
    },
    hardBreak(state, node, parent, index) {
      for (let i = index + 1; i < parent.childCount; i++) {
        if (parent.child(i).type !== node.type) { state.write('\\\n'); return }
      }
    },
    horizontalRule(state, node) {
      state.write((node.attrs.markup as string) || '---'); state.closeBlock(node)
    },
    // Block image → ![alt](src "title"). #118: alt is escaped so a "]" can't
    // break the syntax, and src/title go through the shared encoders — a src
    // holding a space or an unbalanced ")" would otherwise close the link early
    // and spill the rest of the URL into the exported document as prose.
    image(state, node) {
      const alt = state.esc((node.attrs.alt as string) || '')
      const title = node.attrs.title ? ` "${markdownTitle(node.attrs.title as string)}"` : ''
      state.write(`![${alt}](${markdownUrl(node.attrs.src as string)}${title})`)
      state.closeBlock(node)
    },
  },
  {
    bold:      { open: '**', close: '**', mixable: true, expelEnclosingWhitespace: true },
    italic:    { open: '*',  close: '*',  mixable: true, expelEnclosingWhitespace: true },
    strike:    { open: '~~', close: '~~', mixable: true, expelEnclosingWhitespace: true },
    code:      { open: '`',  close: '`',  escape: false, expelEnclosingWhitespace: true },
    // No native Markdown syntax → inline HTML (renders in GFM). Highlight uses
    // the "==" convention supported by Pandoc/many renderers.
    highlight:   { open: '==',    close: '==',     mixable: true, expelEnclosingWhitespace: true },
    underline:   { open: '<u>',   close: '</u>',   mixable: true, expelEnclosingWhitespace: true },
    subscript:   { open: '<sub>', close: '</sub>', mixable: true, expelEnclosingWhitespace: true },
    superscript: { open: '<sup>', close: '</sup>', mixable: true, expelEnclosingWhitespace: true },
    // Font color rides on the textStyle mark → inline <span> (renders in GFM,
    // round-trips back via TextStyle's parseHTML). Empty when it carries no color.
    textStyle: {
      open: (_state, mark) => (mark.attrs.color ? `<span style="color:${mark.attrs.color as string}">` : ''),
      close: (_state, mark) => (mark.attrs.color ? '</span>' : ''),
    },
    link: {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      open: (_state, _mark, _parent, _index) => '[',
      close: (_state, mark) =>
        `](${markdownUrl(mark.attrs.href as string)}` +
        `${mark.attrs.title ? ` "${markdownTitle(mark.attrs.title as string)}"` : ''})`,
    },
  },
)

export function serializeToMarkdown(doc: any): string { // eslint-disable-line @typescript-eslint/no-explicit-any
  return _docSerializer.serialize(doc)
}

/** #118: the image node has no `isAllowedUri` equivalent, so the policy is
 *  applied where the attribute becomes an actual `src`. A document stored before
 *  the policy existed still loads and still shows its alt text — it just does not
 *  get to make the browser fetch whatever it points at. */
const SafeImage = Image.extend({
  addAttributes() {
    const parent = this.parent?.() ?? {}
    return {
      ...parent,
      src: {
        ...(parent as Record<string, object>).src,
        renderHTML: (attrs: Record<string, unknown>) => {
          const src = typeof attrs.src === 'string' ? attrs.src : ''
          return isAllowedImageSrc(src) ? { src } : {}
        },
      },
    }
  },
})

const DOC_TYPES = ['note', 'spec', 'research', 'plan', 'reference', 'canvas', 'other'] as const

// A doc_type-locked panel (Notes) reuses this whole surface; only the wording changes.
// ponytail: two forms is all the copy needs — no i18n/pluralization lib for "doc"/"note".
function nouns(docType?: string) {
  const noun = docType ?? 'doc'
  return { noun, Noun: noun[0].toUpperCase() + noun.slice(1) }
}

// ---------------------------------------------------------------------------
// Doc list view
// ---------------------------------------------------------------------------

/** Swatch keys, mirroring DOC_COLORS in apps/api/app/core/constants.py. */
const NOTE_COLORS = ['yellow', 'orange', 'red', 'green', 'teal', 'blue', 'purple', 'gray'] as const

/** Keep-style swatch row. 'default' is the sentinel that clears the colour server-side. */
function NoteColors(
  { doc, onChanged, onStale }: { doc: DocSummary; onChanged: (d: Doc) => void; onStale: () => void },
) {
  const pick = (key: string) => {
    if ((doc.color ?? 'default') === key) return
    api.docs.update(doc.id, { color: key, version: doc.version })
      .then(onChanged)
      // Almost always a 409 from a concurrent edit — refetch so the row stops lying.
      .catch(onStale)
  }
  return (
    <div className="ab-notecard-colors">
      <button type="button" className="ab-swatch" title="No colour"
        aria-label="No colour" aria-pressed={!doc.color} onClick={() => pick('default')} />
      {NOTE_COLORS.map(c => (
        <button key={c} type="button" className="ab-swatch" data-color={c}
          title={c} aria-label={c} aria-pressed={doc.color === c} onClick={() => pick(c)} />
      ))}
    </div>
  )
}

/**
 * Keep's "Take a note…" bar: type a title, press Enter, land in the editor.
 * ponytail: a plain input, not an expanding inline rich-text composer — the
 * editor is one keystroke away and already does everything.
 */
function NoteComposer(
  { projectId, docType, onCreated }: { projectId: string; docType: string; onCreated: (d: Doc) => void },
) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = () => {
    const t = title.trim()
    if (!t || busy) return
    setBusy(true); setError(null)
    api.docs.create(projectId, { title: t, doc_type: docType })
      .then(d => { setTitle(''); onCreated(d) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="ab-note-composer">
      <input className="input" type="text" value={title} disabled={busy}
        placeholder={`Take a ${nouns(docType).noun}…`} aria-label={`New ${nouns(docType).noun} title`}
        onChange={e => setTitle(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); create() } }} />
      <button type="button" className="btn btn-solid btn-sm" disabled={!title.trim() || busy}
        onClick={create}>{busy ? 'Adding…' : 'Add'}</button>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

interface DocListProps {
  projectId: string
  onSelect: (doc: DocSummary) => void
  onNew: () => void
  onClose?: () => void
  docType?: string
}

function DocList({ projectId, onSelect, onNew, onClose, docType }: DocListProps) {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')      // debounced copy of `search`
  const { noun, Noun } = nouns(docType)

  // Debounce so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQuery(search), 200)
    return () => clearTimeout(t)
  }, [search])

  const reload = useCallback(() => {
    setError(null)
    api.docs.list(projectId, { ...(docType ? { doc_type: docType } : {}), q: query })
      .then(setDocs)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId, docType, query])

  useEffect(() => { setLoading(true); reload() }, [reload])

  const searching = query.trim().length > 0

  // Keep-ish: an always-present composer instead of a button that swaps the view.
  const composer = docType ? (
    <NoteComposer projectId={projectId} docType={docType} onCreated={onSelect} />
  ) : null

  const searchBox = (
    <input className="input dp-search" type="search" value={search}
      placeholder={`Search ${noun}s…`} aria-label={`Search ${noun}s`}
      onChange={e => setSearch(e.target.value)} />
  )

  if (error) return <p className="dp-state dp-error">{error}</p>

  return (
    <div>
      <div className="dp-list-header">
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          {docs.length} {docs.length === 1 ? noun : `${noun}s`}
        </div>
        {searchBox}
        {!docType && <button className="btn btn-solid btn-sm" onClick={onNew}>+ New {Noun}</button>}
        {onClose && <button type="button" className="btn btn-ghost btn-sm" title={`Close ${noun}s`} onClick={onClose}>✕</button>}
      </div>
      {composer}
      {loading ? <p className="dp-state">Loading {noun}s…</p>
        : searching && docs.length === 0 ? (
        <p className="dp-state">No {noun}s match “{query}”.</p>
      ) : docs.length === 0 ? (
        <div className="ab-empty">
          <div className="ab-empty-art">
            <svg className="ic-32" aria-hidden="true"><use href="#icon-file" /></svg>
          </div>
          <h3>No {noun}s yet</h3>
          <p>{docType === 'note'
            ? 'Jot down anything — meeting notes, ideas, snippets.'
            : 'Create your first doc to capture specs, plans, or research.'}</p>
          {/* Notes already have the composer directly above — no second button. */}
          {!docType && <button className="btn btn-solid btn-sm" onClick={onNew}>Create a {noun}</button>}
        </div>
      ) : docType ? (
        // Google-Keep-style card grid — the locked-type (Notes) view only; Docs keeps its list.
        <div className="ab-notegrid">
          {docs.map(d => (
            <div key={d.id} className="ab-notecard" data-color={d.color ?? undefined}>
              {/* Only this region opens the note, so the swatch buttons below
                  aren't nested inside a role="button". */}
              <div className="ab-notecard-open" role="button" tabIndex={0}
                onClick={() => onSelect(d)}
                onKeyDown={e => e.key === 'Enter' && onSelect(d)}>
                <div className="ab-notecard-title">{d.title}</div>
                {d.excerpt?.trim()
                  ? <div className="ab-notecard-body">{d.excerpt}</div>
                  : <div className="ab-notecard-body ab-notecard-empty">Empty {noun}</div>}
              </div>
              <div className="ab-notecard-foot">
                <StatusBadge kind="docstatus" value={d.status} />
                <span className="ab-notecard-date">{agoLabel(d.updated_at)}</span>
              </div>
              <div className="ab-notecard-tools">
                <NoteColors doc={d} onStale={reload} onChanged={updated =>
                  setDocs(prev => prev.map(x => (x.id === updated.id ? { ...x, ...updated } : x)))} />
                <button type="button" className="ab-note-del" title={`Delete ${noun}`}
                  aria-label={`Delete ${d.title}`}
                  onClick={() => {
                    if (!window.confirm(`Delete “${d.title}”? This can't be undone.`)) return
                    api.docs.remove(d.id)
                      .then(() => setDocs(prev => prev.filter(x => x.id !== d.id)))
                      .catch(reload)
                  }}>
                  <svg className="ic-14" aria-hidden="true"><use href="#icon-trash" /></svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="ab-doclist">
          {docs.map(d => (
            <div key={d.id} className="ab-docitem" role="button" tabIndex={0}
              data-color={d.color ?? undefined}
              onClick={() => onSelect(d)}
              onKeyDown={e => e.key === 'Enter' && onSelect(d)}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ab-doc-name">{d.title}</div>
                <div className="ab-doc-meta">
                  <span className="badge badge-neutral badge-sm">{d.doc_type}</span>
                </div>
              </div>
              <StatusBadge kind="docstatus" value={d.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create doc form
// ---------------------------------------------------------------------------

interface CreateDocFormProps {
  projectId: string
  onCreated: (doc: Doc) => void
  onCancel: () => void
  lockedType?: string
}

function CreateDocForm({ projectId, onCreated, onCancel, lockedType }: CreateDocFormProps) {
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState<string>(lockedType ?? 'note')
  const { Noun } = nouns(lockedType)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true); setError(null)
    // A 'canvas' doc is an Excalidraw whiteboard; any other type is a Tiptap doc.
    const editor_format = docType === 'canvas' ? 'excalidraw' : undefined
    api.docs.create(projectId, { title: title.trim(), doc_type: docType, editor_format })
      .then(onCreated)
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false))
  }

  return (
    <div>
      <div className="dp-list-header">
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
          New {lockedType ?? 'document'}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      <form className="dp-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label className="form-label">Title</label>
          <input className="input" type="text" placeholder={`${Noun} title`} value={title}
            onChange={e => setTitle(e.target.value)} required autoFocus />
        </div>
        {!lockedType && (
          <div className="form-field">
            <label className="form-label">Type</label>
            <select className="input select" value={docType} onChange={e => setDocType(e.target.value)}>
              {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="dp-form-actions">
          <button type="submit" disabled={saving || !title.trim()} className="btn btn-solid btn-sm">
            {saving ? 'Creating…' : 'Create'}
          </button>
          <button type="button" className="btn btn-outline btn-sm" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tiptap toolbar
// ---------------------------------------------------------------------------

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null

  // Prompt for a URL; empty input removes the link. extendMarkRange lets the
  // command act on the whole link even when the cursor is just inside it.
  const setLink = () => {
    const prev = editor.getAttributes('link').href as string | undefined
    const url = window.prompt('Link URL', prev ?? 'https://')
    if (url === null) return // cancelled
    const chain = editor.chain().focus().extendMarkRange('link')
    if (url.trim() === '') { chain.unsetLink().run(); return }
    // #118: the same rule the server enforces, applied while the author is still
    // here to fix it — otherwise the refusal arrives as a 422 on the next save,
    // long after they typed it.
    if (!isAllowedLink(url.trim(), { allowRelative: true })) {
      window.alert('Links must be http(s), mailto:, or a path within this app.')
      return
    }
    chain.setLink({ href: url.trim() }).run()
  }

  // Insert an image by URL; prompt for alt text (accessibility).
  const addImage = () => {
    const url = window.prompt('Image URL')
    if (!url || !url.trim()) return
    if (!isAllowedImageSrc(url.trim())) {
      window.alert('Image sources must be http(s) or a base64 data URI (png, jpeg, gif, webp, avif).')
      return
    }
    const alt = window.prompt('Alt text (describe the image)') ?? ''
    editor.chain().focus().setImage({ src: url.trim(), alt }).run()
  }

  return (
    // Prevent a toolbar button's mousedown from blurring the editor and
    // collapsing the selection — otherwise toggleBold/Italic/etc. apply to an
    // empty cursor instead of the selected text. The color <input> is exempt so
    // its native picker still opens.
    <div className="ab-toolbar" role="toolbar" aria-label="Editor toolbar"
      onMouseDown={(e) => { if ((e.target as HTMLElement).closest('button')) e.preventDefault() }}>
      <button type="button" title="Bold"
        className={`ab-tbtn${editor.isActive('bold') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleBold().run()}>B</button>
      <button type="button" title="Italic"
        className={`ab-tbtn${editor.isActive('italic') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleItalic().run()}><span className="ab-tbtn-it" aria-hidden="true">I</span></button>
      <button type="button" title="Underline"
        className={`ab-tbtn${editor.isActive('underline') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleUnderline().run()}><u aria-hidden="true">U</u></button>
      <button type="button" title="Strikethrough"
        className={`ab-tbtn${editor.isActive('strike') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleStrike().run()}><s aria-hidden="true">S</s></button>
      <button type="button" title="Highlight"
        className={`ab-tbtn${editor.isActive('highlight') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleHighlight().run()}><mark aria-hidden="true">H</mark></button>
      <button type="button" title="Subscript"
        className={`ab-tbtn${editor.isActive('subscript') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleSubscript().run()}>X<sub aria-hidden="true">2</sub></button>
      <button type="button" title="Superscript"
        className={`ab-tbtn${editor.isActive('superscript') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleSuperscript().run()}>X<sup aria-hidden="true">2</sup></button>
      <span className="ab-tdiv" />
      <button type="button" title="Heading 1"
        className={`ab-tbtn${editor.isActive('heading', { level: 1 }) ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}>H1</button>
      <button type="button" title="Heading 2"
        className={`ab-tbtn${editor.isActive('heading', { level: 2 }) ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>H2</button>
      <span className="ab-tdiv" />
      <button type="button" title="Bullet list"
        className={`ab-tbtn${editor.isActive('bulletList') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleBulletList().run()}>•</button>
      <button type="button" title="Ordered list"
        className={`ab-tbtn${editor.isActive('orderedList') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}>1.</button>
      <button type="button" title="Task list"
        className={`ab-tbtn${editor.isActive('taskList') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleTaskList().run()}>☑</button>
      <button type="button" title="Blockquote"
        className={`ab-tbtn${editor.isActive('blockquote') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}>❝</button>
      <button type="button" title="Code block"
        className={`ab-tbtn${editor.isActive('codeBlock') ? ' active' : ''}`}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}>{'{}'}</button>
      <span className="ab-tdiv" />
      <button type="button" title="Link"
        className={`ab-tbtn${editor.isActive('link') ? ' active' : ''}`}
        onClick={setLink}>🔗</button>
      <button type="button" title="Image"
        className="ab-tbtn"
        onClick={addImage}>🖼</button>
      <input type="color" className="ab-tcolor" title="Font color" aria-label="Font color"
        value={(editor.getAttributes('textStyle').color as string) || '#000000'}
        onChange={(e) => editor.chain().focus().setColor(e.target.value).run()} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Markdown preview (safe — uses pre, NOT dangerouslySetInnerHTML)
// ---------------------------------------------------------------------------

function MarkdownPreview({ markdown }: { markdown: string }) {
  if (!markdown) return <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', padding: 'var(--space-6) var(--space-8)', margin: 0 }}>No markdown content yet.</p>
  return <pre className="dp-md-preview">{markdown}</pre>
}

// ---------------------------------------------------------------------------
// Doc editor
// ---------------------------------------------------------------------------

/**
 * Turn a pasted/dropped image into an inline data URI.
 *
 * ponytail: data URIs, no upload endpoint and no blob store — the note IS the
 * image's home. The ceiling is real though: content_json is capped at 2 MB
 * server-side, so anything sizeable is downscaled first, and a single image that
 * still won't fit is rejected here rather than failing the save later. Upgrade
 * path if notes become image-heavy: a real upload endpoint + /media/{id} refs.
 */
const IMAGE_PASSTHROUGH_BYTES = 400 * 1024   // small enough to embed untouched
const IMAGE_MAX_EDGE = 1400
const IMAGE_MAX_DATA_URL = 1_200_000         // ~1.2 MB of base64, inside the 2 MB doc cap

function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result as string)
    fr.onerror = () => reject(new Error('Could not read the image'))
    fr.readAsDataURL(file)
  })
}

async function imageToDataUrl(file: File): Promise<string> {
  if (file.size <= IMAGE_PASSTHROUGH_BYTES) return readAsDataUrl(file)

  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, IMAGE_MAX_EDGE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  // JPEG: a pasted screenshot as PNG is several times larger for no visible gain.
  const out = canvas.toDataURL('image/jpeg', 0.8)
  if (out.length > IMAGE_MAX_DATA_URL) {
    throw new Error('That image is too large to embed — resize it and try again.')
  }
  return out
}

// #118: an SVG is a document, not a raster — it would be inlined as a data URI
// and become a markup surface we then have to sanitize. The server refuses one,
// so accepting it here would only produce a save that fails.
const imageFilesOf = (dt: DataTransfer | null | undefined): File[] =>
  Array.from(dt?.files ?? []).filter(
    f => f.type.startsWith('image/') && f.type !== 'image/svg+xml',
  )

interface DocEditorProps { docId: string; onBack: () => void }
type SaveState = 'saved' | 'unsaved' | 'saving' | 'conflict' | 'error'

function DocEditor({ docId, onBack }: DocEditorProps) {
  const [doc, setDoc] = useState<Doc | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [exportMsg, setExportMsg] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const versionRef = useRef<number>(1)
  const docRef = useRef<Doc | null>(null)
  const titleRef = useRef('')
  // Paste/drop handlers are built once inside useEditor, before `editor` exists.
  const editorRef = useRef<ReturnType<typeof useEditor> | null>(null)

  // P11.2 soft-lock (dormant in local mode — the presence surface 404s).
  const { lockedByOther, editorName } = usePresence(docId, true)

  const editor = useEditor({
    extensions: [
      // StarterKit v3 bundles Link + Underline; configure/enable them here
      // rather than adding second extensions (which triggers duplicate-name warnings).
      StarterKit.configure({
        link: {
          openOnClick: false,
          autolink: true,
          HTMLAttributes: { rel: 'noopener noreferrer nofollow', target: '_blank' },
          // #118: an explicit policy rather than the extension's default. Tiptap
          // 3.28 fixed its own URI validation, but a library default is not
          // something to depend on for a security property — and this must agree
          // with what the server stores, which the default knows nothing about.
          isAllowedUri: (url: string) => isAllowedLink(url, { allowRelative: true }),
        },
      }),
      TextStyle,
      Color,
      Highlight,
      Subscript,
      Superscript,
      TaskList,
      TaskItem.configure({ nested: true }),
      SafeImage,
    ],
    content: '',
    onUpdate: () => setSaveState('unsaved'),
    editorProps: {
      // Images arrive as files on both paths, so both share one handler. Returning
      // false for anything else leaves ProseMirror's native text paste/drop alone —
      // which is what makes dragging plain text in already work.
      handlePaste: (_view, event) => insertImages(imageFilesOf(event.clipboardData)),
      handleDrop: (view, event) => {
        const files = imageFilesOf((event as DragEvent).dataTransfer)
        if (files.length === 0) return false
        // Drop where the pointer is, not at the caret — otherwise the image lands
        // wherever you last typed, and a selected node gets replaced outright.
        const at = view.posAtCoords({
          left: (event as DragEvent).clientX,
          top: (event as DragEvent).clientY,
        })
        return insertImages(files, at?.pos)
      },
    },
  })
  editorRef.current = editor

  /** True = we took the files. Insertion is async; the handlers must answer now. */
  function insertImages(files: File[], at?: number): boolean {
    if (files.length === 0) return false
    void (async () => {
      let pos = at
      for (const file of files) {
        try {
          const src = await imageToDataUrl(file)
          const node = { type: 'image', attrs: { src, alt: file.name } }
          // Explicit position for the first dropped file; the caret has moved past
          // it by the time the next one lands, so the rest just follow the cursor.
          if (pos != null) editorRef.current?.chain().focus().insertContentAt(pos, node).run()
          else editorRef.current?.chain().focus().setImage({ src, alt: file.name }).run()
          pos = undefined
        } catch (e: unknown) {
          setSaveError(e instanceof Error ? e.message : String(e))
          setSaveState('error')
        }
      }
    })()
    return true
  }

  useEffect(() => {
    editor?.setEditable(!lockedByOther)
  }, [editor, lockedByOther])

  useEffect(() => {
    setLoading(true); setLoadError(null)
    api.docs.get(docId)
      .then(d => {
        setDoc(d); docRef.current = d; versionRef.current = d.version
        setTitle(d.title); titleRef.current = d.title
        if (editor) {
          let parsed: object | null = null
          try { parsed = JSON.parse(d.content_json) } catch { /* ignore */ }
          if (parsed) editor.commands.setContent(parsed as never)
        }
        setSaveState('saved')
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false))
  }, [docId, editor])

  const save = useCallback(async () => {
    if (!editor || !docRef.current) return
    const contentJson = JSON.stringify(editor.getJSON())
    const markdownCache = serializeToMarkdown(editor.state.doc)
    const nextTitle = titleRef.current.trim()
    setSaveState('saving'); setSaveError(null)
    try {
      const updated = await api.docs.update(docRef.current.id, {
        version: versionRef.current,
        content_json: contentJson,
        markdown_cache: markdownCache,
        // Only when it actually changed — an empty box must not blank the title.
        ...(nextTitle && nextTitle !== docRef.current.title ? { title: nextTitle } : {}),
      })
      setDoc(updated); docRef.current = updated; versionRef.current = updated.version
      // Edits made *during* the request would otherwise be marked clean and sit
      // unsaved until the next keystroke.
      const settled =
        JSON.stringify(editor.getJSON()) === contentJson && titleRef.current.trim() === nextTitle
      setSaveState(settled ? 'saved' : 'unsaved')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setSaveState('conflict')
      else { setSaveState('error'); setSaveError(msg) }
    }
  }, [editor])

  // Autosave: one debounced write per pause in typing. 'conflict' and 'error' are
  // deliberately excluded — retrying on a loop would hammer a doomed request.
  useEffect(() => {
    if (saveState !== 'unsaved' || lockedByOther) return
    const t = setTimeout(() => { void save() }, 900)
    return () => clearTimeout(t)
  }, [saveState, save, lockedByOther])

  const rename = (next: string) => {
    setTitle(next); titleRef.current = next
    if (next.trim() && next.trim() !== docRef.current?.title) setSaveState('unsaved')
  }

  const remove = () => {
    if (!docRef.current) return
    if (!window.confirm(`Delete “${docRef.current.title}”? This can't be undone.`)) return
    api.docs.remove(docRef.current.id)
      .then(onBack)
      .catch((e: Error) => { setSaveError(e.message); setSaveState('error') })
  }

  // A colour PATCH bumps the doc version server-side, so adopt the new version
  // here or the next content save 409s against a version we just invalidated.
  // Unsaved editor content is untouched: only the load effect ever sets content.
  const applyColor = useCallback((updated: Doc) => {
    setDoc(updated); docRef.current = updated; versionRef.current = updated.version
  }, [])

  const exportMarkdown = useCallback(async () => {
    if (!doc) return
    setExportMsg(null)
    try {
      const res = await api.docs.exportMarkdown(doc.id)
      setExportMsg(res.was_changed ? `Exported to ${res.export_path}` : 'No changes (file up-to-date)')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setExportMsg('The exported file was changed outside Planarus. Review it before exporting again.')
      else setExportMsg(`Export failed: ${msg}`)
    }
  }, [doc])

  if (loading) return <p className="dp-state">Loading doc…</p>
  if (loadError) return <p className="dp-state dp-error">{loadError}</p>
  if (!doc) return <p className="dp-state dp-error">Doc not found.</p>

  const saveLabel =
    saveState === 'saving'  ? 'Saving…' :
    saveState === 'saved'   ? 'Saved' :
    saveState === 'unsaved' ? 'Unsaved changes' :
    saveState === 'conflict' ? '⚠ Updated elsewhere — refresh to reload' :
    `Error: ${saveError ?? 'unknown'}`

  return (
    <div className="ab-editor" data-color={doc.color ?? undefined}>
      <div className="dp-editor-nav" style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)' }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to list">← Back</button>
        {/* The title is the note's section heading — edit in place, autosaved. */}
        <input className="dp-title-input" type="text" value={title} disabled={lockedByOther}
          aria-label="Title" placeholder="Untitled"
          onChange={e => rename(e.target.value)}
          onBlur={() => { if (!title.trim()) rename(doc.title) }} />
        <StatusBadge kind="docstatus" value={doc.status} />
        {/* Swatches only where the colour is actually rendered — the Notes grid. */}
        {doc.doc_type === 'note' && !lockedByOther && (
          <NoteColors doc={doc} onChanged={applyColor} onStale={() => setSaveState('conflict')} />
        )}
        {lockedByOther && (
          <span
            className="badge badge-warning badge-sm"
            title="Someone else holds the edit lock; this doc is read-only until they leave"
          >
            🔒 {editorName} is editing — read-only
          </span>
        )}
      </div>

      <EditorToolbar editor={editor} />

      <div className="dp-tiptap-wrap">
        {showPreview
          ? <MarkdownPreview markdown={doc.markdown_cache} />
          : <div className="ab-prose"><EditorContent editor={editor} className="dp-tiptap" /></div>
        }
      </div>

      <div className="dp-statusbar">
        <span className={`dp-save-label ${saveState}`}>{saveLabel}</span>
        {doc.updated_by_display && (
          <span className="dp-edited-by" style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
            Last edited by {doc.updated_by_display}
          </span>
        )}
        <button type="button" className="btn btn-outline btn-xs"
          onClick={save} disabled={saveState === 'saving' || saveState === 'saved'}>Save</button>
        <button type="button" className="btn btn-ghost btn-xs"
          onClick={() => setShowPreview(p => !p)}>
          {showPreview ? 'Editor' : 'Preview'}
        </button>
        <button type="button" className="btn btn-ghost btn-xs" onClick={() => exportMarkdown()}>
          Export Markdown
        </button>
        <button type="button" className="btn btn-ghost btn-xs dp-danger" onClick={remove}>
          Delete
        </button>
      </div>
      {exportMsg && <p className="dp-export-msg">{exportMsg}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Root panel
// ---------------------------------------------------------------------------

/** `docType` locks the panel to one type — the Notes view is this panel with docType="note". */
interface DocsPanelProps { projectId: string; onClose: () => void; docType?: string }

export default function DocsPanel({ projectId, onClose, docType }: DocsPanelProps) {
  const [view, setView] = useState<'list' | 'new' | 'editor'>('list')
  const [selected, setSelected] = useState<{ id: string; format: string } | null>(null)

  const handleSelect = (doc: DocSummary) => { setSelected({ id: doc.id, format: doc.editor_format }); setView('editor') }
  const handleCreated = (doc: Doc) => { setSelected({ id: doc.id, format: doc.editor_format }); setView('editor') }

  return (
    <div className="dp-panel">
      {view === 'list' && <DocList projectId={projectId} onSelect={handleSelect} onNew={() => setView('new')} onClose={onClose} docType={docType} />}
      {view === 'new' && <CreateDocForm projectId={projectId} onCreated={handleCreated} onCancel={() => setView('list')} lockedType={docType} />}
      {view === 'editor' && selected && (
        selected.format === 'excalidraw'
          ? <Suspense fallback={<p className="dp-state">Loading canvas…</p>}>
              <CanvasEditor docId={selected.id} onBack={() => setView('list')} />
            </Suspense>
          : <DocEditor docId={selected.id} onBack={() => setView('list')} />
      )}
    </div>
  )
}
