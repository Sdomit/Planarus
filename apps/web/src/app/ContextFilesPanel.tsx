import { useEffect, useState } from 'react'
import { api, ContextFile, Project } from '../api/client'
import './context-files-panel.css'

export default function ContextFilesPanel({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null)
  const [files, setFiles] = useState<ContextFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState(false)
  const [pinning, setPinning] = useState<string | null>(null)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [projectId])

  async function load() {
    setLoading(true); setError(null)
    try {
      const proj = await api.projects.get(projectId)
      setProject(proj)
      setFiles(await api.contextFiles.list(proj.id))
    } catch {
      setError('Could not load context files. Make sure the backend is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  async function regenerate() {
    if (!project) return
    setRegenerating(true); setError(null)
    try {
      await api.contextFiles.regenerate(project.id)
      setFiles(await api.contextFiles.list(project.id))
    } catch (e) {
      setError(String(e))
    } finally {
      setRegenerating(false)
    }
  }

  async function togglePin(file: ContextFile) {
    setPinning(file.id)
    try {
      const updated = await api.contextFiles.setPinned(file.id, !file.pinned)
      setFiles(prev => prev.map(f => f.id === updated.id ? updated : f))
    } catch (e) {
      setError(String(e))
    } finally {
      setPinning(null)
    }
  }

  if (loading) return <p className="cf-state">Loading context files…</p>

  if (error) {
    return (
      <div className="cf-state cf-error">
        <p>{error}</p>
        <button className="btn btn-outline btn-sm" onClick={load}>Retry</button>
      </div>
    )
  }

  if (!project) return null

  return (
    <div className="cf-panel">
      <div className="cf-toolbar">
        <span className="cf-project-name">{project.title}</span>
        <button className="btn btn-outline btn-sm" onClick={regenerate}
          disabled={regenerating || !project.folder_path}>
          {regenerating ? 'Regenerating…' : 'Regenerate'}
        </button>
      </div>

      {!project.folder_path && (
        <p className="cf-note">No folder path set — set one in project settings to generate context files.</p>
      )}

      {files.length === 0 ? (
        <div className="ab-empty">
          <div className="ab-empty-art">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="6" width="32" height="36" rx="4" fill="var(--bg-subtle)" stroke="var(--border-default)" strokeWidth="2"/>
              <path d="M16 16h16M16 22h16M16 28h10" stroke="var(--text-tertiary)" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="36" cy="36" r="8" fill="var(--bg-canvas)" stroke="var(--border-default)" strokeWidth="2"/>
              <path d="M36 32v8M32 36h8" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <h3>No context files yet</h3>
          <p>Context files give AI agents a snapshot of your project — code structure, decisions, docs, and tasks — so they can answer questions without reading the whole repo.</p>
          {project.folder_path && (
            <button className="btn btn-solid btn-sm" onClick={regenerate} disabled={regenerating}>
              {regenerating ? 'Generating…' : 'Generate now'}
            </button>
          )}
        </div>
      ) : (
        <ul className="cf-list">
          {files.map(f => (
            <li key={f.id} className="cf-item">
              <div className="cf-item-head">
                <span className="cf-path">{f.relative_path.replace('context/', '')}</span>
                <button className="btn btn-ghost btn-xs" onClick={() => togglePin(f)}
                  disabled={pinning === f.id} aria-pressed={f.pinned}>
                  {f.pinned ? '📌 Pinned' : 'Pin'}
                </button>
              </div>
              <div className="cf-meta">
                <span className="cf-kind">{f.kind}</span>
                {f.last_manual_edit_at && <span className="cf-drift">drifted</span>}
                <span className="cf-time">{f.generated_at.slice(0, 16).replace('T', ' ')}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
