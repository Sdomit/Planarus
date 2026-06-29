import { useEffect, useState, type FormEvent } from 'react'
import { api, Project, Workspace, Task, Risk } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { Icon } from './Icon'
import './dashboard.css'

const PROJECT_STATUSES = [
  'idea', 'researching', 'planning', 'ready', 'active',
  'blocked', 'paused', 'later', 'review', 'done', 'archived',
]
const DONE_TASK = new Set(['done', 'canceled'])

function slugify(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'my-project'
}
function initials(s: string): string {
  return s.replace(/[^a-zA-Z0-9 ]/g, '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || 'PR'
}
function splitName(title: string): { code: string; rest: string } {
  const m = title.split(/\s+[-—:]\s+/)
  return m.length > 1 ? { code: m[0], rest: m.slice(1).join(' ') } : { code: title, rest: '' }
}

interface ProjAgg { project: Project; tasks: Task[]; risks: Risk[]; done: number; total: number; pct: number }
interface DashboardProps { onSelectProject?: (p: { id: string; title: string; slug: string }) => void }

export default function Dashboard({ onSelectProject }: DashboardProps) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [aggs, setAggs] = useState<ProjAgg[]>([])
  const [pending, setPending] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ title: '', slug: '', status: 'idea', summary: '' })

  useEffect(() => { loadData() }, [])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const workspaces = await api.workspaces.list()
      const ws = workspaces[0] ?? null
      setWorkspace(ws)
      if (ws) {
        const projs = await api.projects.list(ws.id)
        const data = await Promise.all(
          projs.map(async (project) => {
            const [tasks, risks] = await Promise.all([
              api.tasks.list(project.id).catch(() => [] as Task[]),
              api.risks.list(project.id).catch(() => [] as Risk[]),
            ])
            const total = tasks.length
            const done = tasks.filter((t) => t.status === 'done').length
            return { project, tasks, risks, done, total, pct: total ? Math.round((done / total) * 100) : 0 }
          }),
        )
        setAggs(data)
        const pend = await api.approvals.list(undefined, 'pending').catch(() => [])
        setPending(pend.length)
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
      loadData()
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (!workspace) return
    setCreating(true)
    try {
      await api.projects.create({
        workspace_id: workspace.id,
        title: form.title,
        slug: form.slug,
        status: form.status,
        summary: form.summary || undefined,
      })
      setShowCreate(false)
      setForm({ title: '', slug: '', status: 'idea', summary: '' })
      loadData()
    } catch (e) {
      setError(String(e))
    } finally {
      setCreating(false)
    }
  }

  if (loading) return <div className="ab-state"><span className="spinner spinner-sm" /> Loading projects…</div>
  if (error) {
    return (
      <div className="ab-state ab-state-error">
        <p style={{ margin: 0 }}>{error}</p>
        <button className="btn btn-outline btn-sm" type="button" onClick={loadData}>Retry</button>
      </div>
    )
  }
  if (!workspace) {
    return (
      <div className="ab-state">
        <p style={{ margin: 0 }}>No workspace found.</p>
        <button className="btn btn-solid btn-sm" type="button" onClick={initWorkspace}>Initialize default workspace</button>
      </div>
    )
  }

  const projects = aggs.map((a) => a.project)
  const activeCount = projects.filter((p) => p.status === 'active').length
  const openTasks = aggs.reduce((n, a) => n + a.tasks.filter((t) => !DONE_TASK.has(t.status)).length, 0)
  const openRisks = aggs.reduce((n, a) => n + a.risks.filter((r) => r.status === 'open').length, 0)
  const criticalRisks = aggs.reduce((n, a) => n + a.risks.filter((r) => r.severity === 'critical').length, 0)

  const kpis = [
    { label: 'Active projects', value: activeCount, foot: `of ${projects.length} total` },
    { label: 'Open tasks', value: openTasks, foot: 'in progress' },
    { label: 'Pending approvals', value: pending, foot: pending ? 'awaiting review' : 'queue clear' },
    { label: 'Open risks', value: openRisks, foot: `${criticalRisks} critical` },
  ]

  return (
    <section className="anim-fade-in-up">
      <div className="ab-section-head">
        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: '-0.015em', margin: 0, color: 'var(--text-primary)' }}>All projects</h2>
        <button className="btn btn-solid btn-md" type="button" onClick={() => setShowCreate(true)}>
          <Icon name="plus" className="ic-14" /> New project
        </button>
      </div>

      <div className="ab-kpis stagger" style={{ marginBottom: 'var(--space-6)' }}>
        {kpis.map((k) => (
          <div className="ab-kpi anim-fade-in-up" key={k.label}>
            <div className="ab-kpi-label">{k.label}</div>
            <div className="ab-kpi-val">{k.value}</div>
            <div className="ab-kpi-foot">{k.foot}</div>
          </div>
        ))}
      </div>

      {projects.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-10)', color: 'var(--text-secondary)' }}>
          No projects yet. Create your first project.
        </div>
      ) : (
        <div className="ab-proj-grid stagger">
          {aggs.map(({ project: p, pct, done, total }) => {
            const nm = splitName(p.title)
            const open = () => onSelectProject?.({ id: p.id, title: p.title, slug: p.slug })
            return (
              <article
                key={p.id}
                className="card card-interactive ab-proj anim-fade-in-up"
                role="button"
                tabIndex={0}
                onClick={open}
                onKeyDown={(e) => { if (e.key === 'Enter') open() }}
              >
                <div className="ab-proj-top">
                  <div className="ab-proj-mark" style={{ background: 'var(--accent-muted)', color: 'var(--text-accent)' }}>{initials(p.title)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="ab-proj-name">{nm.code}</div>
                    <div className="ab-proj-sub">{nm.rest || p.slug}</div>
                  </div>
                  <StatusBadge kind="project" value={p.status} />
                </div>
                {p.summary && <div className="ab-proj-desc">{p.summary}</div>}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 6 }}>
                    <span>{done}/{total} tasks</span><span>{pct}%</span>
                  </div>
                  <div className="ab-meter"><span style={{ width: `${pct}%` }} /></div>
                </div>
                <div className="ab-proj-foot">
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Updated {new Date(p.updated_at).toLocaleDateString()}</span>
                  {p.priority && <StatusBadge kind="priority" value={p.priority} />}
                </div>
              </article>
            )
          })}
        </div>
      )}

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">New project</h2>
              <button className="modal-close" type="button" aria-label="Close" onClick={() => setShowCreate(false)}>
                <Icon name="x" className="ic-18" />
              </button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div className="form-field">
                  <label className="form-label" htmlFor="np-title">Title</label>
                  <input id="np-title" className="input" required value={form.title}
                    onChange={(e) => setForm((f) => ({ ...f, title: e.target.value, slug: slugify(e.target.value) }))}
                    placeholder="Project title" />
                </div>
                <div className="form-field">
                  <label className="form-label" htmlFor="np-slug">Slug</label>
                  <input id="np-slug" className="input" required value={form.slug}
                    onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
                    pattern="[a-z0-9][a-z0-9\-]*[a-z0-9]" title="Lowercase letters, numbers, and hyphens" />
                </div>
                <div className="form-field">
                  <label className="form-label" htmlFor="np-status">Status</label>
                  <select id="np-status" className="input select" value={form.status}
                    onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
                    {PROJECT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div className="form-field">
                  <label className="form-label" htmlFor="np-sum">Summary</label>
                  <input id="np-sum" className="input" value={form.summary}
                    onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))} placeholder="Optional" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowCreate(false)}>Cancel</button>
                <button type="submit" className="btn btn-solid btn-sm" disabled={creating}>{creating ? 'Creating…' : 'Create project'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  )
}
