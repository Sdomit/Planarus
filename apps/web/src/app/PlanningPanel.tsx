import { useEffect, useRef, useState } from 'react'
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
const BLOCKER_STATUSES = ['open', 'resolved', 'canceled']

type BoardCol = { key: string; label: string; statuses: string[]; dot: string }

// "Flow" board: the 4 Microsoft-Planner-style buckets.
const BOARD_COLS: BoardCol[] = [
  { key: 'backlog',  label: 'Backlog',  statuses: ['backlog'],                            dot: 'var(--text-tertiary)' },
  { key: 'active',   label: 'Active',   statuses: ['ready', 'in_progress'],               dot: 'var(--status-info-fg)' },
  { key: 'review',   label: 'Review',   statuses: ['waiting', 'needs_review', 'blocked'], dot: 'var(--status-warning-fg)' },
  { key: 'done',     label: 'Done',     statuses: ['done', 'canceled'],                   dot: 'var(--status-success-fg)' },
]

// "Status" board: one column per canonical status (matches the list's statuses).
const STATUS_DOT: Record<string, string> = {
  backlog: 'var(--text-tertiary)', ready: 'var(--status-info-fg)', in_progress: 'var(--status-info-fg)',
  waiting: 'var(--status-warning-fg)', needs_review: 'var(--status-warning-fg)', blocked: 'var(--status-danger-fg)',
  done: 'var(--status-success-fg)', canceled: 'var(--text-tertiary)',
}
const STATUS_COLS: BoardCol[] = TASK_STATUSES.map(s => ({
  key: s, label: s.replace(/_/g, ' '), statuses: [s], dot: STATUS_DOT[s] ?? 'var(--text-tertiary)',
}))

/** Status a task takes when dropped on `col`; null when it already fits there (no change / no write). */
export function nextStatusForColumn(taskStatus: string, col: Pick<BoardCol, 'statuses'>): string | null {
  return col.statuses.includes(taskStatus) ? null : col.statuses[0]
}

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

        {tab === 'phases' && (
          <PhasesList phases={phases} onPhaseUpdated={updated =>
            setPhases(prev => prev.map(p => p.id === updated.id ? updated : p))
          } />
        )}
        {tab === 'tasks' && (
          <TasksList tasks={tasks} phases={phases} stages={stages} projectId={project.id} onTaskUpdated={updated =>
            setTasks(prev => prev.map(task => task.id === updated.id ? updated : task))
          } />
        )}
        {tab === 'milestones' && (
          <MilestonesList milestones={milestones} onMilestoneUpdated={updated =>
            setMilestones(prev => prev.map(m => m.id === updated.id ? updated : m))
          } />
        )}
        {tab === 'decisions' && (
          <DecisionsList decisions={decisions} onDecisionUpdated={updated =>
            setDecisions(prev => prev.map(d => d.id === updated.id ? updated : d))
          } />
        )}
        {tab === 'risks' && (
          <RisksList
            risks={risks}
            blockers={openBlockers}
            onRiskUpdated={updated => setRisks(prev => prev.map(r => r.id === updated.id ? updated : r))}
            onBlockerUpdated={updated => setBlockers(prev => prev.map(b => b.id === updated.id ? updated : b))}
          />
        )}
        {tab === 'comments' && <CommentsList comments={comments} />}
        {tab === 'links' && <LinksList links={links} />}
      </div>
    </div>
  )
}

const EMPTY = { color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 } as const

/** Generic click-to-expand row shell: header stays visible, detail body toggles below it. */
function ExpandableRow({
  id, header, children, className = '',
}: { id: string; header: React.ReactNode; children: React.ReactNode; className?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`pp-row pp-row-expandable${className ? ` ${className}` : ''}`}>
      <button
        type="button"
        className="pp-row-main"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls={`row-details-${id}`}
      >
        <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        {header}
      </button>
      {open && <div className="pp-task-details" id={`row-details-${id}`}>{children}</div>}
    </li>
  )
}

/** Shared PATCH-and-report-error plumbing for a single expandable row's edit controls. */
function useRowUpdate<T>(updateFn: (patch: Partial<T>) => Promise<T>, onUpdated: (t: T) => void) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const update = async (patch: Partial<T>) => {
    setSaving(true); setError(null)
    try {
      onUpdated(await updateFn(patch))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }
  return { saving, error, update }
}

function PhasesList({ phases, onPhaseUpdated }: { phases: Phase[]; onPhaseUpdated: (p: Phase) => void }) {
  if (phases.length === 0) return <p style={EMPTY}>No phases yet.</p>
  return (
    <ul className="pp-rows">
      {phases.map(ph => (
        <PhaseRow key={ph.id} phase={ph} onUpdated={onPhaseUpdated} />
      ))}
    </ul>
  )
}

function PhaseRow({ phase, onUpdated }: { phase: Phase; onUpdated: (p: Phase) => void }) {
  const { saving, error, update } = useRowUpdate(patch => api.phases.update(phase.id, patch), onUpdated)
  return (
    <ExpandableRow
      id={phase.id}
      header={<>
        <span className="pp-row-title">{phase.title}</span>
        <StatusBadge kind="phase" value={phase.status} />
      </>}
    >
      {phase.description && <p className="pp-row-desc">{phase.description}</p>}
      <div className="pp-task-controls" role="group" aria-label={`Edit ${phase.title}`}>
        <label>
          <span>Status</span>
          <select className="input select input-sm" value={phase.status} disabled={saving}
            onChange={e => void update({ status: e.target.value })}>
            {PHASE_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </ExpandableRow>
  )
}

interface TasksListProps {
  tasks: Task[]
  phases: Phase[]
  stages: Stage[]
  projectId: string
  onTaskUpdated: (task: Task) => void
}

// List filter: 'open' = not done/canceled (default), 'all' = everything, else an exact status.
const LIST_FILTERS = ['open', 'all', ...TASK_STATUSES]

function TasksList({ tasks, phases, stages, projectId, onTaskUpdated }: TasksListProps) {
  const [view, setView] = useState<'list' | 'board'>('list')
  const [filter, setFilter] = useState('open')
  const done = tasks.filter(t => t.status === 'done' || t.status === 'canceled').length

  if (tasks.length === 0) return <p style={EMPTY}>No tasks yet.</p>

  const shown = tasks.filter(t => {
    if (filter === 'all') return true
    if (filter === 'open') return t.status !== 'done' && t.status !== 'canceled'
    return t.status === filter
  })

  return (
    <>
      <div className="pp-toolbar">
        <div className="pp-toolbar-group">
          <div className="ab-seg">
            <button type="button" aria-pressed={view === 'list'} className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button>
            <button type="button" aria-pressed={view === 'board'} className={view === 'board' ? 'active' : ''} onClick={() => setView('board')}>Board</button>
          </div>
          {view === 'list' && (
            <select className="input select input-sm" aria-label="Filter tasks" value={filter} onChange={e => setFilter(e.target.value)}>
              {LIST_FILTERS.map(f => (
                <option key={f} value={f}>{f === 'open' ? 'Open' : f === 'all' ? 'All' : f.replace(/_/g, ' ')}</option>
              ))}
            </select>
          )}
        </div>
        {done > 0 && <span className="pp-done-lbl">{done} done</span>}
      </div>

      {view === 'board' ? (
        <TaskBoard tasks={tasks} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated} />
      ) : shown.length === 0 ? (
        <p style={EMPTY}>No tasks match this filter.</p>
      ) : (
        <ul className="pp-rows">
          {shown.map(t => (
            <TaskRow key={t.id} task={t} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated} />
          ))}
        </ul>
      )}
    </>
  )
}

/** Kanban board with two groupings (Flow buckets / per-status), drag-to-restatus, and click-to-open. */
function TaskBoard({ tasks, phases, stages, projectId, onTaskUpdated }: TasksListProps) {
  const [group, setGroup] = useState<'flow' | 'status'>('flow')
  const [openId, setOpenId] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [overCol, setOverCol] = useState<string | null>(null)
  const cols = group === 'flow' ? BOARD_COLS : STATUS_COLS
  const phaseTitle = new Map(phases.map(phase => [phase.id, phase.title]))
  const openTask = tasks.find(t => t.id === openId) ?? null

  async function dropOn(col: BoardCol) {
    setOverCol(null)
    const id = dragId
    setDragId(null)
    if (!id) return
    const task = tasks.find(t => t.id === id)
    if (!task) return
    const status = nextStatusForColumn(task.status, col)
    if (!status) return
    try {
      onTaskUpdated(await api.tasks.update(id, { status }))
    } catch {
      /* leave the card where it was on failure */
    }
  }

  return (
    <>
      <div className="pp-toolbar">
        <div className="ab-seg" role="group" aria-label="Board grouping">
          <button type="button" aria-pressed={group === 'flow'} className={group === 'flow' ? 'active' : ''} onClick={() => setGroup('flow')}>Flow</button>
          <button type="button" aria-pressed={group === 'status'} className={group === 'status' ? 'active' : ''} onClick={() => setGroup('status')}>Status</button>
        </div>
        <span className="pp-done-lbl">Drag a card to change its status</span>
      </div>
      <div className="pp-board-wrap">
        <div className="ab-board">
          {cols.map(col => {
            const colTasks = tasks.filter(t => col.statuses.includes(t.status))
            return (
              <div
                key={col.key}
                className={`ab-col${overCol === col.key ? ' ab-col-over' : ''}`}
                onDragOver={e => { e.preventDefault(); if (overCol !== col.key) setOverCol(col.key) }}
                onDragLeave={() => setOverCol(c => (c === col.key ? null : c))}
                onDrop={() => void dropOn(col)}
              >
                <div className="ab-col-head">
                  <span className="ab-col-dot" style={{ background: col.dot }} />
                  <span className="ab-col-title">{col.label}</span>
                  <span className="ab-col-count">{colTasks.length}</span>
                </div>
                {colTasks.map(t => (
                  <div
                    key={t.id}
                    className="ab-task-card"
                    draggable
                    role="button"
                    tabIndex={0}
                    onDragStart={() => setDragId(t.id)}
                    onDragEnd={() => { setDragId(null); setOverCol(null) }}
                    onClick={() => setOpenId(t.id)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); setOpenId(t.id) } }}
                  >
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
      {openTask && (
        <TaskDialog task={openTask} phases={phases} stages={stages} projectId={projectId}
          onClose={() => setOpenId(null)} onTaskUpdated={onTaskUpdated} />
      )}
    </>
  )
}

/** Card detail as a native modal dialog (Esc / backdrop / ✕ all close it). */
function TaskDialog({ task, phases, stages, projectId, onClose, onTaskUpdated }: {
  task: Task; phases: Phase[]; stages: Stage[]; projectId: string
  onClose: () => void; onTaskUpdated: (task: Task) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal?.() }, [])
  const close = () => ref.current?.close()
  return (
    <dialog
      ref={ref}
      className="pp-dialog"
      onClose={onClose}
      onClick={e => { if (e.target === ref.current) close() }}
    >
      <div className="pp-dialog-head">
        <span className="pp-dialog-title">{task.title}</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={close} aria-label="Close">✕</button>
      </div>
      <TaskDetailBody task={task} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated} />
    </dialog>
  )
}

/** Shared task detail: status/priority/phase/stage controls, checklist, and comments. */
function TaskDetailBody({ task, phases, stages, projectId, onTaskUpdated }: {
  task: Task; phases: Phase[]; stages: Stage[]; projectId: string; onTaskUpdated: (task: Task) => void
}) {
  const [items, setItems] = useState<ChecklistItem[]>([])
  const [label, setLabel] = useState('')
  const [saving, setSaving] = useState(false)
  const [taskError, setTaskError] = useState<string | null>(null)
  const taskStages = task.phase_id ? stages.filter(stage => stage.phase_id === task.phase_id) : []

  useEffect(() => { void api.checklistItems.list(task.id).then(setItems) }, [task.id])

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

  return (
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
      <TaskComments projectId={projectId} taskId={task.id} />
    </div>
  )
}

/** Task-scoped comment thread (reuses the project comments API with entity_type='task'). */
function TaskComments({ projectId, taskId }: { projectId: string; taskId: string }) {
  const [comments, setComments] = useState<Comment[]>([])
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void api.comments.list(projectId, { entity_type: 'task', entity_id: taskId }).then(setComments)
  }, [projectId, taskId])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!body.trim()) return
    setSaving(true)
    try {
      const c = await api.comments.create(projectId, { entity_type: 'task', entity_id: taskId, body: body.trim() })
      setComments(prev => [...prev, c]); setBody('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pp-comments">
      <p className="pp-section-lbl">Comments</p>
      {comments.map(c => (
        <div key={c.id} className="pp-comment">
          <span className="pp-comment-body">{c.body}</span>
          <span className="pp-comment-meta">{c.author_type} · {c.created_at.slice(0, 10)}</span>
        </div>
      ))}
      <form className="pp-comment-add" onSubmit={add}>
        <textarea className="input" placeholder="Add a comment…" aria-label="Add a comment"
          value={body} onChange={e => setBody(e.target.value)} />
        <button type="submit" className="btn btn-outline btn-sm" disabled={saving} style={{ alignSelf: 'flex-start' }}>
          {saving ? 'Saving…' : 'Comment'}
        </button>
      </form>
    </div>
  )
}

/** A task row that expands to reveal the shared task detail (controls, checklist, comments). */
function TaskRow({ task, phases, stages, projectId, onTaskUpdated }: {
  task: Task; phases: Phase[]; stages: Stage[]; projectId: string; onTaskUpdated: (task: Task) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <li className="pp-row pp-row-expandable">
      <button
        type="button"
        className="pp-row-main"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls={`task-details-${task.id}`}
      >
        <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="pp-row-title">{task.title}</span>
        <StatusBadge kind="task" value={task.status} />
      </button>
      {open && <TaskDetailBody task={task} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated} />}
    </li>
  )
}

function MilestonesList({ milestones, onMilestoneUpdated }: { milestones: Milestone[]; onMilestoneUpdated: (m: Milestone) => void }) {
  if (milestones.length === 0) return <p style={EMPTY}>No milestones yet.</p>
  const sorted = [...milestones].sort((a, b) =>
    (a.target_date || '9999-99-99').localeCompare(b.target_date || '9999-99-99') || a.sort_order - b.sort_order)
  return (
    <ul className="pp-rows">
      {sorted.map(m => (
        <MilestoneRow key={m.id} milestone={m} onUpdated={onMilestoneUpdated} />
      ))}
    </ul>
  )
}

function MilestoneRow({ milestone, onUpdated }: { milestone: Milestone; onUpdated: (m: Milestone) => void }) {
  const { saving, error, update } = useRowUpdate(patch => api.milestones.update(milestone.id, patch), onUpdated)
  return (
    <ExpandableRow
      id={milestone.id}
      header={<>
        <span className="pp-row-title">{milestone.title}</span>
        {milestone.target_date && <span className="pp-meta">{milestone.target_date}</span>}
        <StatusBadge kind="milestone" value={milestone.status} />
      </>}
    >
      {milestone.description && <p className="pp-row-desc">{milestone.description}</p>}
      <div className="pp-task-controls" role="group" aria-label={`Edit ${milestone.title}`}>
        <label>
          <span>Status</span>
          <select className="input select input-sm" value={milestone.status} disabled={saving}
            onChange={e => void update({ status: e.target.value })}>
            {MILESTONE_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label>
          <span>Target date</span>
          <input type="date" className="input input-sm" value={milestone.target_date ?? ''} disabled={saving}
            onChange={e => void update({ target_date: e.target.value || null })} />
        </label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </ExpandableRow>
  )
}

function DecisionsList({ decisions, onDecisionUpdated }: { decisions: Decision[]; onDecisionUpdated: (d: Decision) => void }) {
  if (decisions.length === 0) return <p style={EMPTY}>No decisions yet.</p>
  return (
    <ul className="pp-rows">
      {decisions.map(d => (
        <DecisionRow key={d.id} decision={d} onUpdated={onDecisionUpdated} />
      ))}
    </ul>
  )
}

function DecisionRow({ decision, onUpdated }: { decision: Decision; onUpdated: (d: Decision) => void }) {
  const { saving, error, update } = useRowUpdate(patch => api.decisions.update(decision.id, patch), onUpdated)
  return (
    <ExpandableRow
      id={decision.id}
      header={<>
        <span className="pp-row-title">{decision.title}</span>
        <StatusBadge kind="decision" value={decision.status} />
      </>}
    >
      <p className="pp-row-desc">{decision.decision}</p>
      {decision.context && <p className="pp-row-desc">{decision.context}</p>}
      <div className="pp-task-controls" role="group" aria-label={`Edit ${decision.title}`}>
        <label>
          <span>Status</span>
          <select className="input select input-sm" value={decision.status} disabled={saving}
            onChange={e => void update({ status: e.target.value })}>
            {DECISION_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </ExpandableRow>
  )
}

function RisksList({
  risks, blockers, onRiskUpdated, onBlockerUpdated,
}: { risks: Risk[]; blockers: Blocker[]; onRiskUpdated: (r: Risk) => void; onBlockerUpdated: (b: Blocker) => void }) {
  const open = risks.filter(r => !['mitigated', 'accepted', 'closed'].includes(r.status))
  if (open.length === 0 && blockers.length === 0)
    return <p style={EMPTY}>No open risks or blockers.</p>
  return (
    <>
      {open.length > 0 && (
        <ul className="pp-rows">
          {open.map(r => (
            <RiskRow key={r.id} risk={r} onUpdated={onRiskUpdated} />
          ))}
        </ul>
      )}
      {blockers.length > 0 && (
        <>
          <p className="pp-section-lbl">Blockers</p>
          <ul className="pp-rows">
            {blockers.map(b => (
              <BlockerRow key={b.id} blocker={b} onUpdated={onBlockerUpdated} />
            ))}
          </ul>
        </>
      )}
    </>
  )
}

function RiskRow({ risk, onUpdated }: { risk: Risk; onUpdated: (r: Risk) => void }) {
  const { saving, error, update } = useRowUpdate(patch => api.risks.update(risk.id, patch), onUpdated)
  return (
    <ExpandableRow
      id={risk.id}
      header={<>
        <span className="pp-row-title">{risk.title}</span>
        <StatusBadge kind="severity" value={risk.severity} />
        <StatusBadge kind="riskstatus" value={risk.status} />
      </>}
    >
      {risk.description && <p className="pp-row-desc">{risk.description}</p>}
      {risk.mitigation && <p className="pp-row-desc"><strong>Mitigation:</strong> {risk.mitigation}</p>}
      <div className="pp-task-controls" role="group" aria-label={`Edit ${risk.title}`}>
        <label>
          <span>Severity</span>
          <select className="input select input-sm" value={risk.severity} disabled={saving}
            onChange={e => void update({ severity: e.target.value })}>
            {RISK_SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select className="input select input-sm" value={risk.status} disabled={saving}
            onChange={e => void update({ status: e.target.value })}>
            {RISK_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </ExpandableRow>
  )
}

function BlockerRow({ blocker, onUpdated }: { blocker: Blocker; onUpdated: (b: Blocker) => void }) {
  const { saving, error, update } = useRowUpdate(patch => api.blockers.update(blocker.id, patch), onUpdated)
  return (
    <ExpandableRow
      id={blocker.id}
      className="pp-row-blocker"
      header={<span className="pp-row-title">{blocker.title}</span>}
    >
      {blocker.description && <p className="pp-row-desc">{blocker.description}</p>}
      <div className="pp-task-controls" role="group" aria-label={`Edit ${blocker.title}`}>
        <label>
          <span>Status</span>
          <select className="input select input-sm" value={blocker.status} disabled={saving}
            onChange={e => void update({ status: e.target.value })}>
            {BLOCKER_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </ExpandableRow>
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
