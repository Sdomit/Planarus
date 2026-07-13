import { useEffect, useState } from 'react'
import {
  api, Blocker, ChecklistItem, Comment, Decision, Link, Milestone, Phase, Project, Risk, Task,
} from '../api/client'
import { StatusBadge } from './StatusBadge'
import './planning-panel.css'

type TabKey = 'phases' | 'tasks' | 'milestones' | 'decisions' | 'risks' | 'comments' | 'links'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'phases', label: 'Phases' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'milestones', label: 'Milestones' },
  { key: 'decisions', label: 'Decisions' },
  { key: 'risks', label: 'Risks' },
  { key: 'comments', label: 'Comments' },
  { key: 'links', label: 'Links' },
]

const PHASE_STATUSES = ['planned', 'active', 'blocked', 'done', 'canceled']
const TASK_STATUSES = ['backlog', 'ready', 'in_progress', 'waiting', 'needs_review', 'blocked', 'done', 'canceled']
const MILESTONE_STATUSES = ['planned', 'active', 'achieved', 'missed', 'canceled']
const DECISION_STATUSES = ['proposed', 'accepted', 'superseded', 'reversed']
const RISK_SEVERITIES = ['low', 'medium', 'high', 'critical']
const RISK_STATUSES = ['open', 'monitoring', 'mitigated', 'accepted', 'closed']

const BOARD_COLS = [
  { key: 'backlog',  label: 'Backlog',  statuses: ['backlog'],                            dot: 'var(--text-tertiary)' },
  { key: 'active',   label: 'Active',   statuses: ['ready', 'in_progress'],               dot: 'var(--status-info-fg)' },
  { key: 'review',   label: 'Review',   statuses: ['waiting', 'needs_review', 'blocked'], dot: 'var(--status-warning-fg)' },
  { key: 'done',     label: 'Done',     statuses: ['done', 'canceled'],                   dot: 'var(--status-success-fg)' },
]

export default function PlanningPanel({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabKey>('phases')

  const [phases, setPhases] = useState<Phase[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [milestones, setMilestones] = useState<Milestone[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [risks, setRisks] = useState<Risk[]>([])
  const [blockers, setBlockers] = useState<Blocker[]>([])
  const [comments, setComments] = useState<Comment[]>([])
  const [links, setLinks] = useState<Link[]>([])

  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [phaseForm, setPhaseForm] = useState({ title: '', status: 'planned' })
  const [taskForm, setTaskForm] = useState({ title: '', status: 'backlog', priority: '' })
  const [milestoneForm, setMilestoneForm] = useState({ title: '', status: 'planned', target_date: '' })
  const [decisionForm, setDecisionForm] = useState({ title: '', decision: '', status: 'proposed' })
  const [riskForm, setRiskForm] = useState({ title: '', severity: 'medium', status: 'open' })
  const [commentForm, setCommentForm] = useState({ body: '' })
  const [linkForm, setLinkForm] = useState({ url: '', title: '' })

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const proj = await api.projects.get(projectId)
      setProject(proj)
      await loadEntities(proj.id)
    } catch {
      setError('Could not load planning data.')
    } finally {
      setLoading(false)
    }
  }

  async function loadEntities(projectId: string) {
    const [ph, tk, mil, dec, rsk, blk, cmt, lnk] = await Promise.all([
      api.phases.list(projectId),
      api.tasks.list(projectId),
      api.milestones.list(projectId),
      api.decisions.list(projectId),
      api.risks.list(projectId),
      api.blockers.list(projectId),
      api.comments.list(projectId),
      api.links.list(projectId),
    ])
    setPhases(ph); setTasks(tk); setMilestones(mil); setDecisions(dec)
    setRisks(rsk); setBlockers(blk); setComments(cmt); setLinks(lnk)
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!project) return
    setCreating(true); setCreateError(null)
    try {
      if (tab === 'phases') {
        const ph = await api.phases.create(project.id, { title: phaseForm.title, status: phaseForm.status })
        setPhases(prev => [...prev, ph]); setPhaseForm({ title: '', status: 'planned' })
      } else if (tab === 'tasks') {
        const tk = await api.tasks.create(project.id, { title: taskForm.title, status: taskForm.status, priority: taskForm.priority || undefined })
        setTasks(prev => [...prev, tk]); setTaskForm({ title: '', status: 'backlog', priority: '' })
      } else if (tab === 'milestones') {
        const mil = await api.milestones.create(project.id, { title: milestoneForm.title, status: milestoneForm.status, target_date: milestoneForm.target_date || undefined })
        setMilestones(prev => [...prev, mil]); setMilestoneForm({ title: '', status: 'planned', target_date: '' })
      } else if (tab === 'decisions') {
        const dec = await api.decisions.create(project.id, { title: decisionForm.title, decision: decisionForm.decision, status: decisionForm.status })
        setDecisions(prev => [dec, ...prev]); setDecisionForm({ title: '', decision: '', status: 'proposed' })
      } else if (tab === 'risks') {
        const rsk = await api.risks.create(project.id, { title: riskForm.title, severity: riskForm.severity, status: riskForm.status })
        setRisks(prev => [...prev, rsk]); setRiskForm({ title: '', severity: 'medium', status: 'open' })
      } else if (tab === 'comments') {
        const cmt = await api.comments.create(project.id, { entity_type: 'project', entity_id: project.id, body: commentForm.body })
        setComments(prev => [...prev, cmt]); setCommentForm({ body: '' })
      } else if (tab === 'links') {
        const lnk = await api.links.create(project.id, { entity_type: 'project', entity_id: project.id, url: linkForm.url, title: linkForm.title || undefined })
        setLinks(prev => [...prev, lnk]); setLinkForm({ url: '', title: '' })
      }
      setShowCreate(false)
    } catch (e) {
      setCreateError(String(e))
    } finally {
      setCreating(false)
    }
  }

  if (loading) return <p className="pp-state">Loading…</p>
  if (error) return (
    <div className="pp-state">
      <p style={{ color: 'var(--status-danger-fg)', margin: 0 }}>{error}</p>
      <button className="btn btn-outline btn-sm" onClick={load}>Retry</button>
    </div>
  )
  if (!project) return null

  const openBlockers = blockers.filter(b => b.status === 'open')

  return (
    <div className="pp-panel">
      <div className="pp-header">
        <span className="pp-project-name">{project.title}</span>
        {openBlockers.length > 0 && (
          <span className="sbadge sbadge--danger">
            <span className="sdot" />
            {openBlockers.length} blocked
          </span>
        )}
      </div>

      <div className="pp-tabs-bar">
        <div className="tabs" role="tablist">
          {TABS.map(t => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`tab${tab === t.key ? ' active' : ''}`}
              onClick={() => { setTab(t.key); setShowCreate(false); setCreateError(null) }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="pp-body">
        <div className="pp-toolbar">
          <button
            className="btn btn-outline btn-sm"
            onClick={() => { setShowCreate(v => !v); setCreateError(null) }}
          >
            {showCreate ? 'Cancel' : '+ Add'}
          </button>
        </div>

        {showCreate && (
          <form className="pp-form" onSubmit={handleCreate}>
            {tab === 'phases' && (
              <>
                <input className="input" required placeholder="Phase title"
                  value={phaseForm.title} onChange={e => setPhaseForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={phaseForm.status}
                  onChange={e => setPhaseForm(f => ({ ...f, status: e.target.value }))}>
                  {PHASE_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'tasks' && (
              <>
                <input className="input" required placeholder="Task title"
                  value={taskForm.title} onChange={e => setTaskForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={taskForm.status}
                  onChange={e => setTaskForm(f => ({ ...f, status: e.target.value }))}>
                  {TASK_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'milestones' && (
              <>
                <input className="input" required placeholder="Milestone title"
                  value={milestoneForm.title} onChange={e => setMilestoneForm(f => ({ ...f, title: e.target.value }))} />
                <input className="input" type="date" aria-label="Target date"
                  value={milestoneForm.target_date} onChange={e => setMilestoneForm(f => ({ ...f, target_date: e.target.value }))} />
                <select className="input select" value={milestoneForm.status}
                  onChange={e => setMilestoneForm(f => ({ ...f, status: e.target.value }))}>
                  {MILESTONE_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'decisions' && (
              <>
                <input className="input" required placeholder="Decision title"
                  value={decisionForm.title} onChange={e => setDecisionForm(f => ({ ...f, title: e.target.value }))} />
                <textarea className="input" required placeholder="What was decided?"
                  value={decisionForm.decision} onChange={e => setDecisionForm(f => ({ ...f, decision: e.target.value }))} />
                <select className="input select" value={decisionForm.status}
                  onChange={e => setDecisionForm(f => ({ ...f, status: e.target.value }))}>
                  {DECISION_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'risks' && (
              <>
                <input className="input" required placeholder="Risk title"
                  value={riskForm.title} onChange={e => setRiskForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={riskForm.severity}
                  onChange={e => setRiskForm(f => ({ ...f, severity: e.target.value }))}>
                  {RISK_SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <select className="input select" value={riskForm.status}
                  onChange={e => setRiskForm(f => ({ ...f, status: e.target.value }))}>
                  {RISK_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'comments' && (
              <textarea className="input" required placeholder="Add a comment on this project…"
                value={commentForm.body} onChange={e => setCommentForm({ body: e.target.value })} />
            )}
            {tab === 'links' && (
              <>
                <input className="input" required type="url" placeholder="https://…"
                  value={linkForm.url} onChange={e => setLinkForm(f => ({ ...f, url: e.target.value }))} />
                <input className="input" placeholder="Title (optional)"
                  value={linkForm.title} onChange={e => setLinkForm(f => ({ ...f, title: e.target.value }))} />
              </>
            )}
            {createError && <p style={{ color: 'var(--status-danger-fg)', fontSize: 'var(--text-xs)', margin: 0 }}>{createError}</p>}
            <button type="submit" disabled={creating} className="btn btn-solid btn-sm" style={{ alignSelf: 'flex-start' }}>
              {creating ? 'Saving…' : 'Save'}
            </button>
          </form>
        )}

        {tab === 'phases' && <PhasesList phases={phases} />}
        {tab === 'tasks' && <TasksList tasks={tasks} />}
        {tab === 'milestones' && <MilestonesList milestones={milestones} />}
        {tab === 'decisions' && <DecisionsList decisions={decisions} />}
        {tab === 'risks' && <RisksList risks={risks} blockers={openBlockers} />}
        {tab === 'comments' && <CommentsList comments={comments} />}
        {tab === 'links' && <LinksList links={links} />}
      </div>
    </div>
  )
}

const EMPTY = { color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 } as const

function PhasesList({ phases }: { phases: Phase[] }) {
  if (phases.length === 0) return <p style={EMPTY}>No phases yet.</p>
  return (
    <ul className="pp-rows">
      {phases.map(ph => (
        <li key={ph.id} className="pp-row">
          <span className="pp-row-title">{ph.title}</span>
          <StatusBadge kind="phase" value={ph.status} />
        </li>
      ))}
    </ul>
  )
}

function TasksList({ tasks }: { tasks: Task[] }) {
  const [view, setView] = useState<'list' | 'board'>('list')
  const active = tasks.filter(t => t.status !== 'done' && t.status !== 'canceled')
  const done = tasks.length - active.length

  if (tasks.length === 0) return <p style={EMPTY}>No tasks yet.</p>

  return (
    <>
      <div className="pp-toolbar">
        <div className="ab-seg">
          <button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button>
          <button className={view === 'board' ? 'active' : ''} onClick={() => setView('board')}>Board</button>
        </div>
        {done > 0 && <span className="pp-done-lbl">{done} done</span>}
      </div>

      {view === 'board' ? (
        <div className="pp-board-wrap">
          <div className="ab-board">
            {BOARD_COLS.map(col => {
              const colTasks = tasks.filter(t => col.statuses.includes(t.status))
              return (
                <div key={col.key} className="ab-col">
                  <div className="ab-col-head">
                    <span className="ab-col-dot" style={{ background: col.dot }} />
                    <span className="ab-col-title">{col.label}</span>
                    <span className="ab-col-count">{colTasks.length}</span>
                  </div>
                  {colTasks.map(t => (
                    <div key={t.id} className="ab-task-card">
                      <div className="ab-task-title">{t.title}</div>
                      <div className="ab-task-foot">
                        <StatusBadge kind="task" value={t.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <ul className="pp-rows">
          {active.map(t => <TaskRow key={t.id} task={t} />)}
        </ul>
      )}
    </>
  )
}

/** A task row that expands to show/edit its checklist items. */
function TaskRow({ task }: { task: Task }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<ChecklistItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [label, setLabel] = useState('')

  async function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next && !loaded) {
      setItems(await api.checklistItems.list(task.id))
      setLoaded(true)
    }
  }

  async function addItem(e: React.FormEvent) {
    e.preventDefault()
    if (!label.trim()) return
    const item = await api.checklistItems.create(task.id, { label: label.trim() })
    setItems(prev => [...prev, item]); setLabel('')
  }

  async function toggleDone(item: ChecklistItem) {
    const updated = await api.checklistItems.update(item.id, { done: !item.done })
    setItems(prev => prev.map(i => (i.id === updated.id ? updated : i)))
  }

  const doneCount = items.filter(i => i.done).length

  return (
    <li className="pp-row pp-row-expandable">
      <div className="pp-row-main" onClick={toggleOpen} role="button" tabIndex={0}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleOpen() } }}>
        <span className="pp-caret">{open ? '▾' : '▸'}</span>
        <span className="pp-row-title">{task.title}</span>
        {loaded && items.length > 0 && <span className="pp-check-count">{doneCount}/{items.length}</span>}
        <StatusBadge kind="task" value={task.status} />
      </div>
      {open && (
        <div className="pp-checklist">
          {items.map(i => (
            <label key={i.id} className="pp-check">
              <input type="checkbox" checked={i.done} onChange={() => toggleDone(i)} />
              <span className={i.done ? 'pp-check-done' : ''}>{i.label}</span>
            </label>
          ))}
          <form className="pp-check-add" onSubmit={addItem}>
            <input className="input" placeholder="Add checklist item…"
              value={label} onChange={e => setLabel(e.target.value)} />
            <button type="submit" className="btn btn-outline btn-sm">Add</button>
          </form>
        </div>
      )}
    </li>
  )
}

function MilestonesList({ milestones }: { milestones: Milestone[] }) {
  if (milestones.length === 0) return <p style={EMPTY}>No milestones yet.</p>
  const sorted = [...milestones].sort((a, b) =>
    (a.target_date || '9999-99-99').localeCompare(b.target_date || '9999-99-99') || a.sort_order - b.sort_order)
  return (
    <ul className="pp-rows">
      {sorted.map(m => (
        <li key={m.id} className="pp-row">
          <span className="pp-row-title">{m.title}</span>
          {m.target_date && <span className="pp-meta">{m.target_date}</span>}
          <StatusBadge kind="milestone" value={m.status} />
        </li>
      ))}
    </ul>
  )
}

function DecisionsList({ decisions }: { decisions: Decision[] }) {
  if (decisions.length === 0) return <p style={EMPTY}>No decisions yet.</p>
  return (
    <ul className="pp-rows">
      {decisions.map(d => (
        <li key={d.id} className="pp-row">
          <span className="pp-row-title">{d.title}</span>
          <StatusBadge kind="decision" value={d.status} />
        </li>
      ))}
    </ul>
  )
}

function RisksList({ risks, blockers }: { risks: Risk[]; blockers: Blocker[] }) {
  const open = risks.filter(r => !['mitigated', 'accepted', 'closed'].includes(r.status))
  if (open.length === 0 && blockers.length === 0)
    return <p style={EMPTY}>No open risks or blockers.</p>
  return (
    <>
      {open.length > 0 && (
        <ul className="pp-rows">
          {open.map(r => (
            <li key={r.id} className="pp-row">
              <span className="pp-row-title">{r.title}</span>
              <StatusBadge kind="severity" value={r.severity} />
              <StatusBadge kind="riskstatus" value={r.status} />
            </li>
          ))}
        </ul>
      )}
      {blockers.length > 0 && (
        <>
          <p className="pp-section-lbl">Blockers</p>
          <ul className="pp-rows">
            {blockers.map(b => (
              <li key={b.id} className="pp-row pp-row-blocker">
                <span className="pp-row-title">{b.title}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}

function CommentsList({ comments }: { comments: Comment[] }) {
  if (comments.length === 0) return <p style={EMPTY}>No comments yet.</p>
  return (
    <ul className="pp-rows">
      {comments.map(c => (
        <li key={c.id} className="pp-row pp-row-stacked">
          <span className="pp-row-body">{c.body}</span>
          <span className="pp-meta">{c.entity_type} · {c.created_at.slice(0, 10)}</span>
        </li>
      ))}
    </ul>
  )
}

function LinksList({ links }: { links: Link[] }) {
  if (links.length === 0) return <p style={EMPTY}>No links yet.</p>
  return (
    <ul className="pp-rows">
      {links.map(l => (
        <li key={l.id} className="pp-row">
          <a className="pp-row-title pp-link" href={l.url} target="_blank" rel="noopener noreferrer">
            {l.title || l.url}
          </a>
          <span className="pp-meta">{l.entity_type}</span>
        </li>
      ))}
    </ul>
  )
}
