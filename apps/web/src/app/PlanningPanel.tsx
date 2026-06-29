import { useEffect, useState } from 'react'
import { api, Blocker, Decision, Phase, Project, Risk, Task } from '../api/client'
import { StatusBadge } from './StatusBadge'
import './planning-panel.css'

type TabKey = 'phases' | 'tasks' | 'decisions' | 'risks'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'phases', label: 'Phases' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'decisions', label: 'Decisions' },
  { key: 'risks', label: 'Risks' },
]

const PHASE_STATUSES = ['planned', 'active', 'blocked', 'done', 'canceled']
const TASK_STATUSES = ['backlog', 'ready', 'in_progress', 'waiting', 'needs_review', 'blocked', 'done', 'canceled']
const DECISION_STATUSES = ['proposed', 'accepted', 'superseded', 'reversed']
const RISK_SEVERITIES = ['low', 'medium', 'high', 'critical']
const RISK_STATUSES = ['open', 'monitoring', 'mitigated', 'accepted', 'closed']

const BOARD_COLS = [
  { key: 'backlog',  label: 'Backlog',  statuses: ['backlog'],                            dot: 'var(--text-tertiary)' },
  { key: 'active',   label: 'Active',   statuses: ['ready', 'in_progress'],               dot: 'var(--status-info-fg)' },
  { key: 'review',   label: 'Review',   statuses: ['waiting', 'needs_review', 'blocked'], dot: 'var(--status-warning-fg)' },
  { key: 'done',     label: 'Done',     statuses: ['done', 'canceled'],                   dot: 'var(--status-success-fg)' },
]

export default function PlanningPanel() {
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabKey>('phases')

  const [phases, setPhases] = useState<Phase[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [risks, setRisks] = useState<Risk[]>([])
  const [blockers, setBlockers] = useState<Blocker[]>([])

  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [phaseForm, setPhaseForm] = useState({ title: '', status: 'planned' })
  const [taskForm, setTaskForm] = useState({ title: '', status: 'backlog', priority: '' })
  const [decisionForm, setDecisionForm] = useState({ title: '', decision: '', status: 'proposed' })
  const [riskForm, setRiskForm] = useState({ title: '', severity: 'medium', status: 'open' })

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const workspaces = await api.workspaces.list()
      const ws = workspaces[0] ?? null
      if (!ws) { setProject(null); return }
      const projects = await api.projects.list(ws.id)
      const proj = projects[0] ?? null
      setProject(proj)
      if (proj) await loadEntities(proj.id)
    } catch {
      setError('Could not load planning data.')
    } finally {
      setLoading(false)
    }
  }

  async function loadEntities(projectId: string) {
    const [ph, tk, dec, rsk, blk] = await Promise.all([
      api.phases.list(projectId),
      api.tasks.list(projectId),
      api.decisions.list(projectId),
      api.risks.list(projectId),
      api.blockers.list(projectId),
    ])
    setPhases(ph); setTasks(tk); setDecisions(dec); setRisks(rsk); setBlockers(blk)
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
      } else if (tab === 'decisions') {
        const dec = await api.decisions.create(project.id, { title: decisionForm.title, decision: decisionForm.decision, status: decisionForm.status })
        setDecisions(prev => [dec, ...prev]); setDecisionForm({ title: '', decision: '', status: 'proposed' })
      } else if (tab === 'risks') {
        const rsk = await api.risks.create(project.id, { title: riskForm.title, severity: riskForm.severity, status: riskForm.status })
        setRisks(prev => [...prev, rsk]); setRiskForm({ title: '', severity: 'medium', status: 'open' })
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
  if (!project) return (
    <div className="pp-state">
      <p style={{ margin: 0 }}>No project yet. Create one in the Dashboard.</p>
    </div>
  )

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
            {createError && <p style={{ color: 'var(--status-danger-fg)', fontSize: 'var(--text-xs)', margin: 0 }}>{createError}</p>}
            <button type="submit" disabled={creating} className="btn btn-solid btn-sm" style={{ alignSelf: 'flex-start' }}>
              {creating ? 'Saving…' : 'Save'}
            </button>
          </form>
        )}

        {tab === 'phases' && <PhasesList phases={phases} />}
        {tab === 'tasks' && <TasksList tasks={tasks} />}
        {tab === 'decisions' && <DecisionsList decisions={decisions} />}
        {tab === 'risks' && <RisksList risks={risks} blockers={openBlockers} />}
      </div>
    </div>
  )
}

function PhasesList({ phases }: { phases: Phase[] }) {
  if (phases.length === 0) return <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 }}>No phases yet.</p>
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

  if (tasks.length === 0) return <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 }}>No tasks yet.</p>

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
          {active.map(t => (
            <li key={t.id} className="pp-row">
              <span className="pp-row-title">{t.title}</span>
              <StatusBadge kind="task" value={t.status} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function DecisionsList({ decisions }: { decisions: Decision[] }) {
  if (decisions.length === 0) return <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 }}>No decisions yet.</p>
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
    return <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 }}>No open risks or blockers.</p>
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
