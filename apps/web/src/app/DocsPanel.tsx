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
    // Block image → ![alt](src "title"). alt is escaped so a "]" can't break the
    // syntax; src is left raw (matches the link handler). ponytail: a src with
    // a literal ")" would need <angle-bracket> wrapping — rare, deferred.
    image(state, node) {
      const alt = state.esc((node.attrs.alt as string) || '')
      const title = node.attrs.title ? ` "${node.attrs.title as string}"` : ''
      state.write(`![${alt}](${node.attrs.src as string}${title})`); state.closeBlock(node)
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
        `](${mark.attrs.href as string}${mark.attrs.title ? ` "${mark.attrs.title as string}"` : ''})`,
    },
  },
)

export function serializeToMarkdown(doc: any): string { // eslint-disable-line @typescript-eslint/no-explicit-any
  return _docSerializer.serialize(doc)
}

const DOC_TYPES = ['note', 'spec', 'research', 'plan', 'reference', 'canvas', 'other'] as const

// ---------------------------------------------------------------------------
// Doc list view
// ---------------------------------------------------------------------------

interface DocListProps {
  projectId: string
  onSelect: (doc: DocSummary) => void
  onNew: () => void
  onClose?: () => void
}

function DocList({ projectId, onSelect, onNew, onClose }: DocListProps) {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true); setError(null)
    api.docs.list(projectId)
      .then(setDocs)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) return <p className="dp-state">Loading docs…</p>
  if (error) return <p className="dp-state dp-error">{error}</p>

  return (
    <div>
      <div className="dp-list-header">
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          {docs.length} {docs.length === 1 ? 'document' : 'documents'}
        </div>
        <button className="btn btn-solid btn-sm" onClick={onNew}>+ New Doc</button>
        {onClose && <button type="button" className="btn btn-ghost btn-sm" title="Close docs" onClick={onClose}>✕</button>}
      </div>
      {docs.length === 0 ? (
        <div className="ab-empty">
          <div className="ab-empty-art">
            <svg className="ic-32" aria-hidden="true"><use href="#icon-file" /></svg>
          </div>
          <h3>No docs yet</h3>
          <p>Create your first doc to capture specs, plans, or research.</p>
          <button className="btn btn-solid btn-sm" onClick={onNew}>Create a doc</button>
        </div>
      ) : (
        <div className="ab-doclist">
          {docs.map(d => (
            <div key={d.id} className="ab-docitem" role="button" tabIndex={0}
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
}

function CreateDocForm({ projectId, onCreated, onCancel }: CreateDocFormProps) {
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState<string>('note')
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
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>New document</span>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      <form className="dp-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label className="form-label">Title</label>
          <input className="input" type="text" placeholder="Doc title" value={title}
            onChange={e => setTitle(e.target.value)} required autoFocus />
        </div>
        <div className="form-field">
          <label className="form-label">Type</label>
          <select className="input select" value={docType} onChange={e => setDocType(e.target.value)}>
            {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
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
    if (url.trim() === '') chain.unsetLink().run()
    else chain.setLink({ href: url.trim() }).run()
  }

  // Insert an image by URL; prompt for alt text (accessibility).
  const addImage = () => {
    const url = window.prompt('Image URL')
    if (!url || !url.trim()) return
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
  const versionRef = useRef<number>(1)
  const docRef = useRef<Doc | null>(null)

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
        },
      }),
      TextStyle,
      Color,
      Highlight,
      Subscript,
      Superscript,
      TaskList,
      TaskItem.configure({ nested: true }),
      Image,
    ],
    content: '',
    onUpdate: () => setSaveState('unsaved'),
  })

  useEffect(() => {
    editor?.setEditable(!lockedByOther)
  }, [editor, lockedByOther])

  useEffect(() => {
    setLoading(true); setLoadError(null)
    api.docs.get(docId)
      .then(d => {
        setDoc(d); docRef.current = d; versionRef.current = d.version
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
    setSaveState('saving'); setSaveError(null)
    try {
      const updated = await api.docs.update(docRef.current.id, { version: versionRef.current, content_json: contentJson, markdown_cache: markdownCache })
      setDoc(updated); docRef.current = updated; versionRef.current = updated.version; setSaveState('saved')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setSaveState('conflict')
      else { setSaveState('error'); setSaveError(msg) }
    }
  }, [editor])

  const exportMarkdown = useCallback(async () => {
    if (!doc) return
    setExportMsg(null)
    try {
      const res = await api.docs.exportMarkdown(doc.id)
      setExportMsg(res.was_changed ? `Exported to ${res.export_path}` : 'No changes (file up-to-date)')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) setExportMsg('The exported file was changed outside Approvo. Review it before exporting again.')
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
    <div className="ab-editor">
      <div className="dp-editor-nav" style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)' }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to list">← Back</button>
        <span className="dp-editor-name">{doc.title}</span>
        <StatusBadge kind="docstatus" value={doc.status} />
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
        <button type="button" className="btn btn-outline btn-xs"
          onClick={save} disabled={saveState === 'saving' || saveState === 'saved'}>Save</button>
        <button type="button" className="btn btn-ghost btn-xs"
          onClick={() => setShowPreview(p => !p)}>
          {showPreview ? 'Editor' : 'Preview'}
        </button>
        <button type="button" className="btn btn-ghost btn-xs" onClick={() => exportMarkdown()}>
          Export Markdown
        </button>
      </div>
      {exportMsg && <p className="dp-export-msg">{exportMsg}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Root panel
// ---------------------------------------------------------------------------

interface DocsPanelProps { projectId: string; onClose: () => void }

export default function DocsPanel({ projectId, onClose }: DocsPanelProps) {
  const [view, setView] = useState<'list' | 'new' | 'editor'>('list')
  const [selected, setSelected] = useState<{ id: string; format: string } | null>(null)

  const handleSelect = (doc: DocSummary) => { setSelected({ id: doc.id, format: doc.editor_format }); setView('editor') }
  const handleCreated = (doc: Doc) => { setSelected({ id: doc.id, format: doc.editor_format }); setView('editor') }

  return (
    <div className="dp-panel">
      {view === 'list' && <DocList projectId={projectId} onSelect={handleSelect} onNew={() => setView('new')} onClose={onClose} />}
      {view === 'new' && <CreateDocForm projectId={projectId} onCreated={handleCreated} onCancel={() => setView('list')} />}
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
