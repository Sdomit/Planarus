import { useCallback, useEffect, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CodeBlock from '@tiptap/extension-code-block'
import Link from '@tiptap/extension-link'
import { MarkdownSerializer } from 'prosemirror-markdown'
import { api, type Doc, type DocSummary } from '../api/client'
import './docs-panel.css'

// ---------------------------------------------------------------------------
// ProseMirror → Markdown serializer (Tiptap camelCase node/mark names)
// ---------------------------------------------------------------------------

const _docSerializer = new MarkdownSerializer(
  {
    doc(state, node) {
      state.renderContent(node)
    },
    paragraph(state, node) {
      state.renderInline(node)
      state.closeBlock(node)
    },
    text(state, node) {
      state.text(node.text ?? '')
    },
    heading(state, node) {
      state.write(state.repeat('#', node.attrs.level as number) + ' ')
      state.renderInline(node)
      state.closeBlock(node)
    },
    blockquote(state, node) {
      state.wrapBlock('> ', null, node, () => state.renderContent(node))
    },
    bulletList(state, node) {
      state.renderList(node, '  ', () => '* ')
    },
    orderedList(state, node) {
      const start = (node.attrs.start as number) || 1
      state.renderList(node, '  ', (i: number) => `${start + i}. `)
    },
    listItem(state, node) {
      state.renderContent(node)
    },
    codeBlock(state, node) {
      state.write('```' + ((node.attrs.language as string) || '') + '\n')
      state.text(node.textContent, false)
      state.ensureNewLine()
      state.write('```')
      state.closeBlock(node)
    },
    hardBreak(state, node, parent, index) {
      for (let i = index + 1; i < parent.childCount; i++) {
        if (parent.child(i).type !== node.type) {
          state.write('\\\n')
          return
        }
      }
    },
    horizontalRule(state, node) {
      state.write((node.attrs.markup as string) || '---')
      state.closeBlock(node)
    },
  },
  {
    bold:   { open: '**', close: '**', mixable: true, expelEnclosingWhitespace: true },
    italic: { open: '*',  close: '*',  mixable: true, expelEnclosingWhitespace: true },
    strike: { open: '~~', close: '~~', mixable: true, expelEnclosingWhitespace: true },
    code:   { open: '`',  close: '`',  escape: false, expelEnclosingWhitespace: true },
    link: {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      open: (_state, _mark, _parent, _index) => '[',
      close: (_state, mark) =>
        `](${mark.attrs.href as string}${mark.attrs.title ? ` "${mark.attrs.title as string}"` : ''})`,
    },
  },
)

// Converts a live ProseMirror document node to Markdown.
// Preserves headings, bold, italic, lists, blockquotes, code blocks, and links.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function serializeToMarkdown(doc: any): string {
  return _docSerializer.serialize(doc)
}

const DOC_TYPES = ['note', 'spec', 'research', 'plan', 'reference', 'other'] as const

// ---------------------------------------------------------------------------
// Doc list view
// ---------------------------------------------------------------------------

interface DocListProps {
  projectId: string
  onSelect: (doc: DocSummary) => void
  onNew: () => void
}

function DocList({ projectId, onSelect, onNew }: DocListProps) {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.docs.list(projectId)
      .then(setDocs)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) return <p className="dp-state">Loading docs…</p>
  if (error) return <p className="dp-state dp-error">{error}</p>

  return (
    <div className="dp-list-view">
      <div className="dp-toolbar">
        <button className="dp-btn-new" onClick={onNew}>+ New Doc</button>
      </div>
      {docs.length === 0 ? (
        <p className="dp-empty">No docs yet. Create one to get started.</p>
      ) : (
        <ul className="dp-list">
          {docs.map(d => (
            <li key={d.id} className="dp-item" onClick={() => onSelect(d)}>
              <span className="dp-item-title">{d.title}</span>
              <span className={`dp-badge dp-badge-${d.doc_type}`}>{d.doc_type}</span>
              <span className={`dp-badge dp-badge-status-${d.status}`}>{d.status}</span>
            </li>
          ))}
        </ul>
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
    setSaving(true)
    setError(null)
    api.docs.create(projectId, { title: title.trim(), doc_type: docType })
      .then(onCreated)
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false))
  }

  return (
    <form className="dp-form" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder="Doc title"
        value={title}
        onChange={e => setTitle(e.target.value)}
        required
        autoFocus
      />
      <select value={docType} onChange={e => setDocType(e.target.value)}>
        {DOC_TYPES.map(t => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
      {error && <p className="dp-form-error">{error}</p>}
      <div className="dp-form-actions">
        <button type="submit" disabled={saving || !title.trim()}>
          {saving ? 'Creating…' : 'Create'}
        </button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tiptap toolbar
// ---------------------------------------------------------------------------

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null
  return (
    <div className="dp-toolbar-editor" role="toolbar" aria-label="Editor toolbar">
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleBold().run()}
        className={editor.isActive('bold') ? 'dp-tool dp-tool-active' : 'dp-tool'}
        title="Bold"
      >B</button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleItalic().run()}
        className={editor.isActive('italic') ? 'dp-tool dp-tool-active' : 'dp-tool'}
        title="Italic"
      ><em>I</em></button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        className={editor.isActive('heading', { level: 1 }) ? 'dp-tool dp-tool-active' : 'dp-tool'}
        title="Heading 1"
      >H1</button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        className={editor.isActive('heading', { level: 2 }) ? 'dp-tool dp-tool-active' : 'dp-tool'}
        title="Heading 2"
      >H2</button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        className={editor.isActive('bulletList') ? 'dp-tool dp-tool-active' : 'dp-tool'}
        title="Bullet list"
      >•</button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        className={editor.isActive('codeBlock') ? 'dp-tool dp-tool-active' : 'dp-tool'}
        title="Code block"
      >{'{}'}</button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Markdown preview (safe — uses pre, NOT dangerouslySetInnerHTML)
// ---------------------------------------------------------------------------

function MarkdownPreview({ markdown }: { markdown: string }) {
  if (!markdown) return <p className="dp-empty">No markdown content yet.</p>
  return (
    <pre className="dp-markdown-preview">{markdown}</pre>
  )
}

// ---------------------------------------------------------------------------
// Doc editor
// ---------------------------------------------------------------------------

interface DocEditorProps {
  docId: string
  onBack: () => void
}

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

  const editor = useEditor({
    extensions: [
      StarterKit,
      CodeBlock,
      Link.configure({ openOnClick: false }),
    ],
    content: '',
    onUpdate: () => {
      setSaveState('unsaved')
    },
  })

  useEffect(() => {
    setLoading(true)
    setLoadError(null)
    api.docs.get(docId)
      .then(d => {
        setDoc(d)
        docRef.current = d
        versionRef.current = d.version
        if (editor) {
          let parsed: object | null = null
          try { parsed = JSON.parse(d.content_json) } catch { /* ignore */ }
          if (parsed) {
            editor.commands.setContent(parsed as never)
          }
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
    setSaveState('saving')
    setSaveError(null)
    try {
      const updated = await api.docs.update(docRef.current.id, {
        version: versionRef.current,
        content_json: contentJson,
        markdown_cache: markdownCache,
      })
      setDoc(updated)
      docRef.current = updated
      versionRef.current = updated.version
      setSaveState('saved')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('409')) {
        setSaveState('conflict')
      } else {
        setSaveState('error')
        setSaveError(msg)
      }
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
      if (msg.startsWith('409')) {
        setExportMsg('The exported Markdown file was changed outside AgentBoard. Review it before exporting again.')
      } else {
        setExportMsg(`Export failed: ${msg}`)
      }
    }
  }, [doc])

  if (loading) return <p className="dp-state">Loading doc…</p>
  if (loadError) return <p className="dp-state dp-error">{loadError}</p>
  if (!doc) return <p className="dp-state dp-error">Doc not found.</p>

  return (
    <div className="dp-editor">
      <div className="dp-editor-header">
        <button className="dp-back" onClick={onBack} title="Back to list">← Back</button>
        <span className="dp-editor-title">{doc.title}</span>
        <span className={`dp-badge dp-badge-${doc.doc_type}`}>{doc.doc_type}</span>
      </div>

      <EditorToolbar editor={editor} />

      <div className="dp-editor-body">
        {showPreview ? (
          <MarkdownPreview markdown={doc.markdown_cache} />
        ) : (
          <EditorContent editor={editor} className="dp-tiptap" />
        )}
      </div>

      <div className="dp-status-bar">
        <span className={`dp-save-state dp-save-${saveState}`}>
          {saveState === 'saving' && 'Saving…'}
          {saveState === 'saved' && 'Saved'}
          {saveState === 'unsaved' && 'Unsaved'}
          {saveState === 'conflict' && '⚠ Updated elsewhere — refresh to reload'}
          {saveState === 'error' && `Error: ${saveError ?? 'unknown'}`}
        </span>
        <button
          type="button"
          className="dp-btn-save"
          onClick={save}
          disabled={saveState === 'saving' || saveState === 'saved'}
        >
          Save
        </button>
        <button
          type="button"
          className="dp-btn-preview"
          onClick={() => setShowPreview(p => !p)}
        >
          {showPreview ? 'Editor' : 'Preview'}
        </button>
        <button
          type="button"
          className="dp-btn-export"
          onClick={() => exportMarkdown()}
        >
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

interface DocsPanelProps {
  projectId: string
  onClose: () => void
}

export default function DocsPanel({ projectId, onClose }: DocsPanelProps) {
  const [view, setView] = useState<'list' | 'new' | 'editor'>('list')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const handleSelect = (doc: DocSummary) => {
    setSelectedId(doc.id)
    setView('editor')
  }

  const handleCreated = (doc: Doc) => {
    setSelectedId(doc.id)
    setView('editor')
  }

  return (
    <div className="dp-panel">
      <div className="dp-panel-header">
        <span className="dp-panel-title">Docs</span>
        {view !== 'list' && (
          <button className="dp-back-list" onClick={() => setView('list')}>← List</button>
        )}
        <button className="dp-close" onClick={onClose} title="Close docs">✕</button>
      </div>

      {view === 'list' && (
        <DocList
          projectId={projectId}
          onSelect={handleSelect}
          onNew={() => setView('new')}
        />
      )}

      {view === 'new' && (
        <CreateDocForm
          projectId={projectId}
          onCreated={handleCreated}
          onCancel={() => setView('list')}
        />
      )}

      {view === 'editor' && selectedId && (
        <DocEditor docId={selectedId} onBack={() => setView('list')} />
      )}
    </div>
  )
}
