import { useEffect, useState } from 'react'
import { api, type ContextFile, type DocSummary } from '../api/client'
import { Markdown } from './markdown'

type Source =
  | { kind: 'context'; id: string; label: string }
  | { kind: 'doc'; id: string; label: string }

export default function MarkdownPreviewPanel({ projectId }: { projectId: string }) {
  const [sources, setSources] = useState<Source[]>([])
  const [selected, setSelected] = useState<string>('') // "<kind>:<id>"
  // null = not loaded yet; '' = loaded and genuinely empty
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [drifted, setDrifted] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setSelected('')
    setMarkdown(null)
    Promise.all([api.contextFiles.list(projectId), api.docs.list(projectId)])
      .then(([files, docs]: [ContextFile[], DocSummary[]]) => {
        setSources([
          ...files.map((f) => ({ kind: 'context' as const, id: f.id, label: f.relative_path })),
          ...docs.map((d) => ({ kind: 'doc' as const, id: d.id, label: `doc: ${d.title}` })),
        ])
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  const open = (value: string) => {
    setSelected(value)
    setMarkdown(null)
    setDrifted(false)
    setCopied(false)
    if (!value) return
    const [kind, id] = value.split(':', 2)
    setError(null)
    if (kind === 'context') {
      api.contextFiles
        .content(id)
        .then((res) => {
          setMarkdown(res.content ?? '')
          setDrifted(res.drifted)
        })
        .catch((e: Error) => setError(e.message))
    } else {
      api.docs
        .get(id)
        .then((doc) => setMarkdown(doc.markdown_cache))
        .catch((e: Error) => setError(e.message))
    }
  }

  const copy = () => {
    navigator.clipboard?.writeText(markdown ?? '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  if (loading) return <p className="dp-state">Loading sources…</p>

  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <div className="card" style={{ padding: 'var(--space-4)', display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}>
        <label className="form-label" htmlFor="mp-source" style={{ margin: 0 }}>Source</label>
        <select
          id="mp-source"
          className="input select"
          style={{ flex: 1, minWidth: 220 }}
          value={selected}
          onChange={(e) => open(e.target.value)}
        >
          <option value="">Select a context file or doc…</option>
          {sources.map((s) => (
            <option key={`${s.kind}:${s.id}`} value={`${s.kind}:${s.id}`}>{s.label}</option>
          ))}
        </select>
        <button type="button" className="btn btn-outline btn-sm" disabled={!markdown} onClick={copy}>
          {copied ? 'Copied ✓' : 'Copy raw'}
        </button>
        <button type="button" className="btn btn-outline btn-sm" disabled={!markdown} onClick={() => window.print()}>
          Print
        </button>
      </div>

      {error && <p className="dp-state dp-error">{error}</p>}
      {drifted && (
        <p className="dp-state" style={{ color: 'var(--status-warning-fg)' }}>
          ⚠ This file was edited on disk after generation — you are previewing the on-disk content.
        </p>
      )}

      {selected && !error && (
        markdown === null
          ? <p className="dp-state">Loading content…</p>
          : markdown
            ? <div className="card" style={{ padding: 'var(--space-6)' }}><Markdown markdown={markdown} /></div>
            : <p className="dp-state">This source has no content yet.</p>
      )}
      {!selected && !error && (
        <div className="ab-empty">
          <h3>Standalone Markdown preview</h3>
          <p>Render any generated context file or exported doc as formatted Markdown.</p>
        </div>
      )}
    </div>
  )
}
