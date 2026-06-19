import { useEffect, useState } from 'react'
import { api, Project, Workspace } from '../api/client'
import './dashboard.css'

const PROJECT_STATUSES = [
  'idea', 'researching', 'planning', 'ready', 'active',
  'blocked', 'paused', 'later', 'review', 'done', 'archived',
]

function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'my-project'
}

export default function Dashboard() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ title: '', slug: '', status: 'idea', summary: '' })

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const workspaces = await api.workspaces.list()
      const ws = workspaces[0] ?? null
      setWorkspace(ws)
      if (ws) {
        const projs = await api.projects.list(ws.id)
        setProjects(projs)
      }
    } catch {
      setError('Could not reach the API. Make sure the backend is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  async function initWorkspace() {
    try {
      const ws = await api.workspaces.create({ name: 'Default Workspace', slug: 'default' })
      setWorkspace(ws)
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!workspace) return
    setCreating(true)
    try {
      const project = await api.projects.create({
        workspace_id: workspace.id,
        title: form.title,
        slug: form.slug,
        status: form.status,
        summary: form.summary || undefined,
      })
      setProjects((prev) => [project, ...prev])
      setShowCreate(false)
      setForm({ title: '', slug: '', status: 'idea', summary: '' })
    } catch (e) {
      setError(String(e))
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return <div className="dashboard-state">Loading projects…</div>
  }

  if (error) {
    return (
      <div className="dashboard-state dashboard-error">
        <p>{error}</p>
        <button onClick={loadData}>Retry</button>
      </div>
    )
  }

  if (!workspace) {
    return (
      <div className="dashboard-state">
        <p>No workspace found.</p>
        <button onClick={initWorkspace}>Initialize default workspace</button>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <div className="dashboard-toolbar">
        <span className="workspace-label">{workspace.name}</span>
        <button className="btn-create" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? 'Cancel' : '+ New project'}
        </button>
      </div>

      {showCreate && (
        <form className="create-form" onSubmit={handleCreate}>
          <input
            required
            placeholder="Project title"
            value={form.title}
            onChange={(e) =>
              setForm((f) => ({ ...f, title: e.target.value, slug: slugify(e.target.value) }))
            }
          />
          <input
            required
            placeholder="slug"
            value={form.slug}
            onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
            pattern="[a-z0-9][a-z0-9\-]*[a-z0-9]"
            title="Lowercase letters, numbers, and hyphens only"
          />
          <select
            value={form.status}
            onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
          >
            {PROJECT_STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input
            placeholder="Summary (optional)"
            value={form.summary}
            onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
          />
          <button type="submit" disabled={creating}>
            {creating ? 'Creating…' : 'Create project'}
          </button>
        </form>
      )}

      {projects.length === 0 ? (
        <p className="empty-state">No projects yet. Create your first project above.</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <li key={p.id} className="project-card">
              <div className="project-title">{p.title}</div>
              <div className="project-meta">
                <span className={`status status-${p.status}`}>{p.status}</span>
                <span className="project-slug">{p.slug}</span>
              </div>
              {p.summary && <p className="project-summary">{p.summary}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
