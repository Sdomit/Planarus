import { useEffect, useState } from 'react'
import {
  api, Blocker, ChecklistItem, Comment, Decision, Link, Milestone, Phase, Project, Risk, Stage, Task,
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
const TASK_PRIORITIES = ['', 'low', 'med', 'high', 'urgent']
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

export default function PlanningPanel({
  projectId,
  initialTab = 'phases',
}: {
  projectId: string
  initialTab?: TabKey
}) {
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabKey>(initialTab)

  const [phases, setPhases] = useState<Phase[]>([])
  const [stages, setStages] = useState<Stage[]>([])
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
  const [taskForm, setTaskForm] = useState({
    title: '', status: 'backlog', priority: '', phase_id: '', stage_id: '',
  })
  const [milestoneForm, setMilestoneForm] = useState({ title: '', status: 'planned', target_date: '' })
  const [decisionForm, setDecisionForm] = useState({ title: '', decision: '', status: 'proposed' })
  const [riskForm, setRiskForm] = useState({ title: '', severity: 'medium', status: 'open' })
  const [commentForm, setCommentForm] = useState({ body: '' })
  const [linkForm, setLinkForm] = useState({ url: '', title: '' })

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  useEffect(() => {
    setTab(initialTab)
    setShowCreate(false)
    setCreateError(null)
  }, [initialTab, projectId])

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
    const [ph, stg, tk, mil, dec, rsk, blk, cmt, lnk] = await Promise.all([
      api.phases.list(projectId),
      api.stages.list(projectId),
      api.tasks.list(projectId),
      api.milestones.list(projectId),
      api.decisions.list(projectId),
      api.risks.list(projectId),
      api.blockers.list(projectId),
      api.comments.list(projectId),
      api.links.list(projectId),
    ])
    setPhases(ph); setStages(stg); setTasks(tk); setMilestones(mil); setDecisions(dec)
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
        const tk = await api.tasks.create(project.id, {
          title: taskForm.title,
          status: taskForm.status,
          priority: taskForm.priority || undefined,
          phase_id: taskForm.phase_id || undefined,
          stage_id: taskForm.stage_id || undefined,
        })
        setTasks(prev => [...prev, tk])
        setTaskForm({ title: '', status: 'backlog', priority: '', phase_id: '', stage_id: '' })
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
  const taskStages = stages.filter(stage => stage.phase_id === taskForm.phase_id)

  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    let next = index
    if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = TABS.length - 1
    else next = (index + (event.key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length
    setTab(TABS[next].key)
    setShowCreate(false)
    setCreateError(null)
    event.currentTarget.parentElement
      ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]
      ?.focus()
  }

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
          {TABS.map((t, index) => (
            <button
              key={t.key}
              id={`planning-tab-${t.key}`}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              aria-controls={`planning-panel-${t.key}`}
              tabIndex={tab === t.key ? 0 : -1}
              className={`tab${tab === t.key ? ' active' : ''}`}
              onClick={() => { setTab(t.key); setShowCreate(false); setCreateError(null) }}
              onKeyDown={event => handleTabKeyDown(event, index)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className="pp-body"
        id={`planning-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`planning-tab-${tab}`}
      >
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
                <input className="input" required placeholder="Phase title" aria-label="Phase title"
                  value={phaseForm.title} onChange={e => setPhaseForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={phaseForm.status} aria-label="Phase status"
                  onChange={e => setPhaseForm(f => ({ ...f, status: e.target.value }))}>
                  {PHASE_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'tasks' && (
              <>
                <input className="input" required placeholder="Task title" aria-label="Task title"
                  value={taskForm.title} onChange={e => setTaskForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={taskForm.status} aria-label="Task status"
                  onChange={e => setTaskForm(f => ({ ...f, status: e.target.value }))}>
                  {TASK_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <select className="input select" value={taskForm.priority} aria-label="Task priority"
                  onChange={e => setTaskForm(f => ({ ...f, priority: e.target.value }))}>
                  {TASK_PRIORITIES.map(p => <option key={p || 'none'} value={p}>{p || 'no priority'}</option>)}
                </select>
                <select className="input select" value={taskForm.phase_id} aria-label="Task phase"
                  onChange={e => setTaskForm(f => ({ ...f, phase_id: e.target.value, stage_id: '' }))}>
                  <option value="">Unphased</option>
                  {phases.map(phase => <option key={phase.id} value={phase.id}>{phase.title}</option>)}
                </select>
                <select className="input select" value={taskForm.stage_id} aria-label="Task stage"
                  disabled={!taskForm.phase_id || taskStages.length === 0}
                  onChange={e => setTaskForm(f => ({ ...f, stage_id: e.target.value }))}>
                  <option value="">No stage</option>
                  {taskStages.map(stage => <option key={stage.id} value={stage.id}>{stage.title}</option>)}
                </select>
              </>
            )}
            {tab === 'milestones' && (
              <>
                <input className="input" required placeholder="Milestone title" aria-label="Milestone title"
                  value={milestoneForm.title} onChange={e => setMilestoneForm(f => ({ ...f, title: e.target.value }))} />
                <input className="input" type="date" aria-label="Target date"
                  value={milestoneForm.target_date} onChange={e => setMilestoneForm(f => ({ ...f, target_date: e.target.value }))} />
                <select className="input select" value={milestoneForm.status} aria-label="Milestone status"
                  onChange={e => setMilestoneForm(f => ({ ...f, status: e.target.value }))}>
                  {MILESTONE_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'decisions' && (
              <>
                <input className="input" required placeholder="Decision title" aria-label="Decision title"
                  value={decisionForm.title} onChange={e => setDecisionForm(f => ({ ...f, title: e.target.value }))} />
                <textarea className="input" required placeholder="What was decided?" aria-label="Decision details"
                  value={decisionForm.decision} onChange={e => setDecisionForm(f => ({ ...f, decision: e.target.value }))} />
                <select className="input select" value={decisionForm.status} aria-label="Decision status"
                  onChange={e => setDecisionForm(f => ({ ...f, status: e.target.value }))}>
                  {DECISION_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'risks' && (
              <>
                <input className="input" required placeholder="Risk title" aria-label="Risk title"
                  value={riskForm.title} onChange={e => setRiskForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={riskForm.severity} aria-label="Risk severity"
                  onChange={e => setRiskForm(f => ({ ...f, severity: e.target.value }))}>
                  {RISK_SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <select className="input select" value={riskForm.status} aria-label="Risk status"
                  onChange={e => setRiskForm(f => ({ ...f, status: e.target.value }))}>
                  {RISK_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            {tab === 'comments' && (
              <textarea className="input" required placeholder="Add a comment on this project…" aria-label="Project comment"
                value={commentForm.body} onChange={e => setCommentForm({ body: e.target.value })} />
            )}
            {tab === 'links' && (
              <>
                <input className="input" required type="url" placeholder="https://…" aria-label="Link URL"
                  value={linkForm.url} onChange={e => setLinkForm(f => ({ ...f, url: e.target.value }))} />
                <input className="input" placeholder="Title (optional)" aria-label="Link title"
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
        {tab === 'tasks' && (
          <TasksList tasks={tasks} phases={phases} stages={stages} onTaskUpdated={updated =>
            setTasks(prev => prev.map(task => task.id === updated.id ? updated : task))
          } />
        )}
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

interface TasksListProps {
  tasks: Task[]
  phases: Phase[]
  stages: Stage[]
  onTaskUpdated: (task: Task) => void
}

function TasksList({ tasks, phases, stages, onTaskUpdated }: TasksListProps) {
  const [view, setView] = useState<'list' | 'board'>('list')
  const active = tasks.filter(t => t.status !== 'done' && t.status !== 'canceled')
  const done = tasks.length - active.length
  const phaseTitle = new Map(phases.map(phase => [phase.id, phase.title]))

  if (tasks.length === 0) return <p style={EMPTY}>No tasks yet.</p>

  return (
    <>
      <div className="pp-toolbar">
        <div className="ab-seg">
          <button type="button" aria-pressed={view === 'list'} className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button>
          <button type="button" aria-pressed={view === 'board'} className={view === 'board' ? 'active' : ''} onClick={() => setView('board')}>Board</button>
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
                        {t.phase_id && <span className="pp-card-phase">{phaseTitle.get(t.phase_id)}</span>}
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
          {active.map(t => (
            <TaskRow
              key={t.id}
              task={t}
              phases={phases}
              stages={stages}
              onTaskUpdated={onTaskUpdated}
            />
          ))}
        </ul>
      )}
    </>
  )
}

/** A task row that expands to show task controls and checklist items. */
interface TaskRowProps {
  task: Task
  phases: Phase[]
  stages: Stage[]
  onTaskUpdated: (task: Task) => void
}

function TaskRow({ task, phases, stages, onTaskUpdated }: TaskRowProps) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<ChecklistItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [label, setLabel] = useState('')
  const [saving, setSaving] = useState(false)
  const [taskError, setTaskError] = useState<string | null>(null)
  const taskStages = task.phase_id ? stages.filter(stage => stage.phase_id === task.phase_id) : []

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

  async function updateTask(patch: Parameters<typeof api.tasks.update>[1]) {
    setSaving(true)
    setTaskError(null)
    try {
      onTaskUpdated(await api.tasks.update(task.id, patch))
    } catch (error) {
      setTaskError(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  const doneCount = items.filter(i => i.done).length

  return (
    <li className="pp-row pp-row-expandable">
      <button
        type="button"
        className="pp-row-main"
        onClick={toggleOpen}
        aria-expanded={open}
        aria-controls={`task-details-${task.id}`}
      >
        <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="pp-row-title">{task.title}</span>
        {loaded && items.length > 0 && <span className="pp-check-count">{doneCount}/{items.length}</span>}
        <StatusBadge kind="task" value={task.status} />
      </button>
      {open && (
        <div className="pp-task-details" id={`task-details-${task.id}`}>
          <div className="pp-task-controls" role="group" aria-label={`Edit ${task.title}`}>
            <label>
              <span>Status</span>
              <select className="input select input-sm" value={task.status} disabled={saving}
                onChange={event => void updateTask({ status: event.target.value })}>
                {TASK_STATUSES.map(status => <option key={status} value={status}>{status}</option>)}
              </select>
            </label>
            <label>
              <span>Priority</span>
              <select className="input select input-sm" value={task.priority ?? ''} disabled={saving}
                onChange={event => void updateTask({ priority: event.target.value || null })}>
                {TASK_PRIORITIES.map(priority => <option key={priority || 'none'} value={priority}>{priority || 'none'}</option>)}
              </select>
            </label>
            <label>
              <span>Phase</span>
              <select className="input select input-sm" value={task.phase_id ?? ''} disabled={saving}
                onChange={event => {
                  const phaseId = event.target.value || null
                  const stageStillFits = stages.some(stage => stage.id === task.stage_id && stage.phase_id === phaseId)
                  void updateTask({ phase_id: phaseId, stage_id: stageStillFits ? task.stage_id : null })
                }}>
                <option value="">Unphased</option>
                {phases.map(phase => <option key={phase.id} value={phase.id}>{phase.title}</option>)}
              </select>
            </label>
            <label>
              <span>Stage</span>
              <select className="input select input-sm" value={task.stage_id ?? ''}
                disabled={saving || !task.phase_id || taskStages.length === 0}
                onChange={event => void updateTask({ stage_id: event.target.value || null })}>
                <option value="">No stage</option>
                {taskStages.map(stage => <option key={stage.id} value={stage.id}>{stage.title}</option>)}
              </select>
            </label>
          </div>
          {taskError && <p className="form-error" role="alert">{taskError}</p>}
          <div className="pp-checklist">
          {items.map(i => (
            <label key={i.id} className="pp-check">
              <input type="checkbox" checked={i.done} onChange={() => toggleDone(i)} />
              <span className={i.done ? 'pp-check-done' : ''}>{i.label}</span>
            </label>
          ))}
          <form className="pp-check-add" onSubmit={addItem}>
            <input className="input" placeholder="Add checklist item…" aria-label={`Add checklist item to ${task.title}`}
              value={label} onChange={e => setLabel(e.target.value)} />
            <button type="submit" className="btn btn-outline btn-sm">Add</button>
          </form>
          </div>
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
