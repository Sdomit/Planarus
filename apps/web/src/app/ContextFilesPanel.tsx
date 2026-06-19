import { useEffect, useState } from 'react'
import { api, ContextFile, Project } from '../api/client'
import './context-files-panel.css'

export default function ContextFilesPanel() {
  const [project, setProject] = useState<Project | null>(null)
  const [files, setFiles] = useState<ContextFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState(false)
  const [pinning, setPinning] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const workspaces = await api.workspaces.list()
      const ws = workspaces[0] ?? null
      if (!ws) {
        setProject(null)
        setFiles([])
        return
      }
      const projects = await api.projects.list(ws.id)
      const proj = projects[0] ?? null
      setProject(proj)
      setFiles(proj ? await api.contextFiles.list(proj.id) : [])
    } catch {
      setError('Could not load context files. Make sure the backend is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  async function regenerate() {
    if (!project) return
    setRegenerating(true)
    setError(null)
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
      setFiles((prev) => prev.map((f) => (f.id === updated.id ? updated : f)))
    } catch (e) {
      setError(String(e))
    } finally {
      setPinning(null)
    }
  }

  if (loading) {
    return <p className="cf-state">Loading context files…</p>
  }

  if (error) {
    return (
      <div className="cf-state cf-error">
        <p>{error}</p>
        <button onClick={load}>Retry</button>
      </div>
    )
  }

  if (!project) {
    return <p className="cf-state">No project yet. Create one to generate its context pack.</p>
  }

  return (
    <div className="cf-panel">
      <div className="cf-toolbar">
        <span className="cf-project">{project.title}</span>
        <button
          className="cf-regen"
          onClick={regenerate}
          disabled={regenerating || !project.folder_path}
        >
          {regenerating ? 'Regenerating…' : 'Regenerate'}
        </button>
      </div>

      {!project.folder_path && (
        <p className="cf-note">No folder path set — this project has no context pack yet.</p>
      )}

      {files.length === 0 ? (
        <p className="cf-note">No context files generated yet.</p>
      ) : (
        <ul className="cf-list">
          {files.map((f) => (
            <li key={f.id} className="cf-item">
              <div className="cf-item-head">
                <span className="cf-path">{f.relative_path.replace('context/', '')}</span>
                <button
                  className={f.pinned ? 'cf-pin pinned' : 'cf-pin'}
                  onClick={() => togglePin(f)}
                  disabled={pinning === f.id}
                >
                  {f.pinned ? '📌 Pinned' : 'Pin'}
                </button>
              </div>
              <div className="cf-meta">
                <span className="cf-kind">{f.kind}</span>
                {f.last_manual_edit_at && <span className="cf-drift">drifted</span>}
                <span className="cf-time">
                  {f.generated_at.slice(0, 16).replace('T', ' ')}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
