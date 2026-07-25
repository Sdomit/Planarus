import { useCallback, useEffect, useState, type FormEvent, type MouseEvent, type ReactNode } from 'react'
import { api, Project, Workspace, Task, Risk } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { Icon } from './Icon'
import {
  UNCATEGORIZED,
  assignCategory,
  categoryOf,
  listCategories,
} from './categories'
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
const stop = (e: MouseEvent) => e.stopPropagation()

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

  // Manage-project state
  const [showArchived, setShowArchived] = useState(false)
  const [activeCat, setActiveCat] = useState<string | null>(null)
  const [cats, setCats] = useState<string[]>(listCategories())
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [moveFor, setMoveFor] = useState<Project | null>(null)
  const [delFor, setDelFor] = useState<Project | null>(null)
  const [delText, setDelText] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const workspaces = await api.workspaces.list()
      const ws = workspaces[0] ?? null
      setWorkspace(ws)
      if (ws) {
        const projs = await api.projects.list(ws.id, showArchived)
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
        setCats(listCategories())
        const pend = await api.approvals.list(undefined, 'pending').catch(() => [])
        setPending(pend.length)
      }
    } catch {
      setError('Could not reach the API. Make sure the backend is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }, [showArchived])

  useEffect(() => { void loadData() }, [loadData])

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

  // Run an action then refresh; errors surface in the banner.
  async function act(fn: () => Promise<unknown>) {
    setMenuFor(null)
    try {
      await fn()
      await loadData()
    } catch (e) {
      setError(String(e))
    }
  }

  async function confirmDelete() {
    if (!delFor) return
    const id = delFor.id
    setDelFor(null)
    setDelText('')
    await act(async () => {
      await api.projects.remove(id)
      assignCategory(id, null)
    })
  }

  function moveTo(category: string | null) {
    if (!moveFor) return
    assignCategory(moveFor.id, category)
    setCats(listCategories())
    setMoveFor(null)
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

  const liveAggs = aggs.filter((a) => !a.project.archived_at)
  const activeCount = liveAggs.filter((a) => a.project.status === 'active').length
  const openTasks = liveAggs.reduce((n, a) => n + a.tasks.filter((t) => !DONE_TASK.has(t.status)).length, 0)
  const openRisks = liveAggs.reduce((n, a) => n + a.risks.filter((r) => r.status === 'open').length, 0)
  const criticalRisks = liveAggs.reduce((n, a) => n + a.risks.filter((r) => r.severity === 'critical').length, 0)

  const kpis = [
    { label: 'Active projects', value: activeCount, foot: `of ${liveAggs.length} total` },
    { label: 'Open tasks', value: openTasks, foot: 'in progress' },
    { label: 'Pending approvals', value: pending, foot: pending ? 'awaiting review' : 'queue clear' },
    { label: 'Open risks', value: openRisks, foot: `${criticalRisks} critical` },
  ]

  const visibleAggs = aggs.filter(({ project: p }) => {
    if (activeCat === null) return true
    const c = categoryOf(p.id)
    return activeCat === UNCATEGORIZED ? c === null : c === activeCat
  })

  return (
    <section className="anim-fade-in-up">
      <div className="ab-section-head">
        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: '-0.015em', margin: 0, color: 'var(--text-primary)' }}>All projects</h2>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <button
            className={`btn btn-sm ${showArchived ? 'btn-outline' : 'btn-ghost'}`}
            type="button"
            onClick={() => setShowArchived((v) => !v)}
          >
            {showArchived ? 'Hide archived' : 'Show archived'}
          </button>
          <button className="btn btn-solid btn-md" type="button" onClick={() => setShowCreate(true)}>
            <Icon name="plus" className="ic-14" /> New project
          </button>
        </div>
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

      {cats.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
          {[
            { key: null as string | null, label: 'All' },
            ...cats.map((c) => ({ key: c as string | null, label: c })),
            { key: UNCATEGORIZED as string | null, label: 'Uncategorized' },
          ].map((chip) => (
            <button
              key={chip.label}
              type="button"
              className={`btn btn-sm ${activeCat === chip.key ? 'btn-solid' : 'btn-ghost'}`}
              onClick={() => setActiveCat(chip.key)}
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {visibleAggs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-10)', color: 'var(--text-secondary)' }}>
          {aggs.length === 0 ? 'No projects yet. Create your first project.' : 'No projects in this view.'}
        </div>
      ) : (
        <div className="ab-proj-grid stagger">
          {visibleAggs.map(({ project: p, pct, done, total }) => {
            const nm = splitName(p.title)
            const cat = categoryOf(p.id)
            const archived = !!p.archived_at
            const open = () => onSelectProject?.({ id: p.id, title: p.title, slug: p.slug })
            return (
              <article
                key={p.id}
                className="card card-interactive ab-proj anim-fade-in-up"
                role="button"
                tabIndex={0}
                onClick={open}
                onKeyDown={(e) => { if (e.key === 'Enter') open() }}
                style={archived ? { opacity: 0.72 } : undefined}
              >
                <div className="ab-proj-top">
                  <div className="ab-proj-mark" style={{ background: 'var(--accent-muted)', color: 'var(--text-accent)' }}>{initials(p.title)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="ab-proj-name">{nm.code}</div>
                    <div className="ab-proj-sub">{nm.rest || p.slug}</div>
                  </div>
                  <StatusBadge kind="project" value={p.status} />
                  <div style={{ position: 'relative' }} onClick={stop}>
                    <button
                      className="btn btn-ghost btn-sm"
                      type="button"
                      aria-label="Project actions"
                      style={{ padding: '2px 8px', lineHeight: 1 }}
                      onClick={() => setMenuFor((m) => (m === p.id ? null : p.id))}
                    >⋯</button>
                    {menuFor === p.id && (
                      <>
                        <div style={{ position: 'fixed', inset: 0, zIndex: 40 }} onClick={() => setMenuFor(null)} />
                        <div
                          role="menu"
                          style={{
                            position: 'absolute', right: 0, top: 'calc(100% + 4px)', zIndex: 41,
                            minWidth: 180, background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-md)', padding: 'var(--space-1)',
                            display: 'flex', flexDirection: 'column',
                          }}
                        >
                          {!archived && <MenuItem onClick={() => act(() => api.projects.update(p.id, { status: 'active' }))}>Set active</MenuItem>}
                          {!archived && <MenuItem onClick={() => act(() => api.projects.update(p.id, { status: 'done' }))}>Set done</MenuItem>}
                          <MenuItem onClick={() => act(() => api.projects.duplicate(p.id))}>Duplicate</MenuItem>
                          <MenuItem onClick={() => { setMenuFor(null); setMoveFor(p) }}>Move to category…</MenuItem>
                          {archived ? (
                            <>
                              <MenuItem onClick={() => act(() => api.projects.unarchive(p.id))}>Restore</MenuItem>
                              <MenuItem danger onClick={() => { setMenuFor(null); setDelFor(p); setDelText('') }}>Delete permanently…</MenuItem>
                            </>
                          ) : (
                            <MenuItem onClick={() => act(() => api.projects.archive(p.id))}>Archive</MenuItem>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>
                {p.summary && <div className="ab-proj-desc">{p.summary}</div>}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 6 }}>
                    <span>{done}/{total} tasks</span><span>{pct}%</span>
                  </div>
                  <div className="ab-meter"><span style={{ width: `${pct}%` }} /></div>
                </div>
                <div className="ab-proj-foot">
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                    {cat ? <span style={{ marginRight: 8, color: 'var(--text-accent)' }}>#{cat}</span> : null}
                    Updated {new Date(p.updated_at).toLocaleDateString()}
                  </span>
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

      {moveFor && (
        <MoveModal
          project={moveFor}
          categories={cats}
          current={categoryOf(moveFor.id)}
          onClose={() => setMoveFor(null)}
          onMove={moveTo}
        />
      )}

      {delFor && (
        <div className="modal-overlay" onClick={() => setDelFor(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Delete project permanently</h2>
              <button className="modal-close" type="button" aria-label="Close" onClick={() => setDelFor(null)}>
                <Icon name="x" className="ic-18" />
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                This <strong>permanently</strong> deletes “{delFor.title}” and all of its tasks, docs,
                decisions, comments, and history. This cannot be undone.
              </p>
              <div className="form-field">
                <label className="form-label" htmlFor="del-confirm">
                  Type <strong>{delFor.title}</strong> to confirm
                </label>
                <input id="del-confirm" className="input" value={delText} autoFocus
                  onChange={(e) => setDelText(e.target.value)} placeholder={delFor.title} />
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDelFor(null)}>Cancel</button>
              <button
                type="button"
                className="btn btn-destructive btn-sm"
                disabled={delText !== delFor.title}
                onClick={confirmDelete}
              >Delete permanently</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function MenuItem({ children, onClick, danger }: { children: ReactNode; onClick: () => void; danger?: boolean }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      style={{
        textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer',
        padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-md)',
        fontSize: 'var(--text-sm)', color: danger ? 'var(--status-danger-fg)' : 'var(--text-primary)',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-muted)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
    >{children}</button>
  )
}

function MoveModal({
  project, categories, current, onClose, onMove,
}: {
  project: Project
  categories: string[]
  current: string | null
  onClose: () => void
  onMove: (category: string | null) => void
}) {
  const [selected, setSelected] = useState<string>(current ?? UNCATEGORIZED)
  const [fresh, setFresh] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    const n = fresh.trim()
    if (n) onMove(n)
    else onMove(selected === UNCATEGORIZED ? null : selected)
  }
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Move “{project.title}”</h2>
          <button className="modal-close" type="button" aria-label="Close" onClick={onClose}>
            <Icon name="x" className="ic-18" />
          </button>
        </div>
        <form onSubmit={submit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              {[UNCATEGORIZED, ...categories].map((c) => (
                <label key={c} style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-sm)', cursor: 'pointer' }}>
                  <input type="radio" name="cat" checked={selected === c && !fresh.trim()} onChange={() => { setSelected(c); setFresh('') }} />
                  {c === UNCATEGORIZED ? 'Uncategorized' : c}
                </label>
              ))}
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="mv-new">Or new category</label>
              <input id="mv-new" className="input" value={fresh}
                onChange={(e) => setFresh(e.target.value)} placeholder="e.g. Clients" />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-solid btn-sm">Move</button>
          </div>
        </form>
      </div>
    </div>
  )
}
