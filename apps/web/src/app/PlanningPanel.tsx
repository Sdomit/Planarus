import { useEffect, useState } from 'react'
import { api, Blocker, Decision, Phase, Project, Risk, Task } from '../api/client'
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
      if (!ws) {
        setProject(null)
        return
      }
      const projects = await api.projects.list(ws.id)
      const proj = projects[0] ?? null
      setProject(proj)
      if (proj) {
        await loadEntities(proj.id)
      }
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
    setPhases(ph)
    setTasks(tk)
    setDecisions(dec)
    setRisks(rsk)
    setBlockers(blk)
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!project) return
    setCreating(true)
    setCreateError(null)
    try {
      if (tab === 'phases') {
        const ph = await api.phases.create(project.id, {
          title: phaseForm.title,
          status: phaseForm.status,
        })
        setPhases((prev) => [...prev, ph])
        setPhaseForm({ title: '', status: 'planned' })
      } else if (tab === 'tasks') {
        const tk = await api.tasks.create(project.id, {
          title: taskForm.title,
          status: taskForm.status,
          priority: taskForm.priority || undefined,
        })
        setTasks((prev) => [...prev, tk])
        setTaskForm({ title: '', status: 'backlog', priority: '' })
      } else if (tab === 'decisions') {
        const dec = await api.decisions.create(project.id, {
          title: decisionForm.title,
          decision: decisionForm.decision,
          status: decisionForm.status,
        })
        setDecisions((prev) => [dec, ...prev])
        setDecisionForm({ title: '', decision: '', status: 'proposed' })
      } else if (tab === 'risks') {
        const rsk = await api.risks.create(project.id, {
          title: riskForm.title,
          severity: riskForm.severity,
          status: riskForm.status,
        })
        setRisks((prev) => [...prev, rsk])
        setRiskForm({ title: '', severity: 'medium', status: 'open' })
      }
      setShowCreate(false)
    } catch (e) {
      setCreateError(String(e))
    } finally {
      setCreating(false)
    }
  }

  if (loading) return <p className="pp-state">Loading…</p>
  if (error)
    return (
      <div className="pp-state pp-error">
        <p>{error}</p>
        <button onClick={load}>Retry</button>
      </div>
    )
  if (!project)
    return <p className="pp-state">No project yet. Create one in the Dashboard.</p>

  const openBlockers = blockers.filter((b) => b.status === 'open')

  return (
    <div className="pp-panel">
      <div className="pp-header">
        <span className="pp-project-name">{project.title}</span>
        {openBlockers.length > 0 && (
          <span className="pp-blocker-badge">{openBlockers.length} blocked</span>
        )}
      </div>

      <div className="pp-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={`pp-tab${tab === t.key ? ' pp-tab-active' : ''}`}
            onClick={() => {
              setTab(t.key)
              setShowCreate(false)
              setCreateError(null)
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="pp-body">
        <div className="pp-toolbar">
          <button
            className="pp-add"
            onClick={() => {
              setShowCreate((v) => !v)
              setCreateError(null)
            }}
          >
            {showCreate ? 'Cancel' : '+ Add'}
          </button>
        </div>

        {showCreate && (
          <form className="pp-form" onSubmit={handleCreate}>
            {tab === 'phases' && (
              <>
                <input
                  required
                  placeholder="Phase title"
                  value={phaseForm.title}
                  onChange={(e) => setPhaseForm((f) => ({ ...f, title: e.target.value }))}
                />
                <select
                  value={phaseForm.status}
                  onChange={(e) => setPhaseForm((f) => ({ ...f, status: e.target.value }))}
                >
                  {PHASE_STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </>
            )}
            {tab === 'tasks' && (
              <>
                <input
                  required
                  placeholder="Task title"
                  value={taskForm.title}
                  onChange={(e) => setTaskForm((f) => ({ ...f, title: e.target.value }))}
                />
                <select
                  value={taskForm.status}
                  onChange={(e) => setTaskForm((f) => ({ ...f, status: e.target.value }))}
                >
                  {TASK_STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </>
            )}
            {tab === 'decisions' && (
              <>
                <input
                  required
                  placeholder="Decision title"
                  value={decisionForm.title}
                  onChange={(e) => setDecisionForm((f) => ({ ...f, title: e.target.value }))}
                />
                <textarea
                  required
                  placeholder="What was decided?"
                  value={decisionForm.decision}
                  onChange={(e) => setDecisionForm((f) => ({ ...f, decision: e.target.value }))}
                />
                <select
                  value={decisionForm.status}
                  onChange={(e) => setDecisionForm((f) => ({ ...f, status: e.target.value }))}
                >
                  {DECISION_STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </>
            )}
            {tab === 'risks' && (
              <>
                <input
                  required
                  placeholder="Risk title"
                  value={riskForm.title}
                  onChange={(e) => setRiskForm((f) => ({ ...f, title: e.target.value }))}
                />
                <select
                  value={riskForm.severity}
                  onChange={(e) => setRiskForm((f) => ({ ...f, severity: e.target.value }))}
                >
                  {RISK_SEVERITIES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <select
                  value={riskForm.status}
                  onChange={(e) => setRiskForm((f) => ({ ...f, status: e.target.value }))}
                >
                  {RISK_STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </>
            )}
            {createError && <p className="pp-form-error">{createError}</p>}
            <button type="submit" disabled={creating}>
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
  if (phases.length === 0) return <p className="pp-empty">No phases yet.</p>
  return (
    <ul className="pp-list">
      {phases.map((ph) => (
        <li key={ph.id} className="pp-item">
          <span className="pp-item-title">{ph.title}</span>
          <span className={`pp-badge pp-badge-${ph.status}`}>{ph.status}</span>
        </li>
      ))}
    </ul>
  )
}

function TasksList({ tasks }: { tasks: Task[] }) {
  const active = tasks.filter((t) => t.status !== 'done' && t.status !== 'canceled')
  const done = tasks.length - active.length
  if (tasks.length === 0) return <p className="pp-empty">No tasks yet.</p>
  return (
    <>
      <ul className="pp-list">
        {active.map((t) => (
          <li key={t.id} className="pp-item">
            <span className="pp-item-title">{t.title}</span>
            <span className={`pp-badge pp-badge-${t.status}`}>{t.status}</span>
          </li>
        ))}
      </ul>
      {done > 0 && <p className="pp-done-count">{done} done</p>}
    </>
  )
}

function DecisionsList({ decisions }: { decisions: Decision[] }) {
  if (decisions.length === 0) return <p className="pp-empty">No decisions yet.</p>
  return (
    <ul className="pp-list">
      {decisions.map((d) => (
        <li key={d.id} className="pp-item">
          <span className="pp-item-title">{d.title}</span>
          <span className={`pp-badge pp-badge-${d.status}`}>{d.status}</span>
        </li>
      ))}
    </ul>
  )
}

function RisksList({ risks, blockers }: { risks: Risk[]; blockers: Blocker[] }) {
  const open = risks.filter((r) => !['mitigated', 'accepted', 'closed'].includes(r.status))
  if (open.length === 0 && blockers.length === 0) return <p className="pp-empty">No open risks or blockers.</p>
  return (
    <>
      {open.length > 0 && (
        <ul className="pp-list">
          {open.map((r) => (
            <li key={r.id} className="pp-item">
              <span className="pp-item-title">{r.title}</span>
              <span className={`pp-badge pp-badge-sev-${r.severity}`}>{r.severity}</span>
            </li>
          ))}
        </ul>
      )}
      {blockers.length > 0 && (
        <>
          <p className="pp-section-label">Blockers</p>
          <ul className="pp-list">
            {blockers.map((b) => (
              <li key={b.id} className="pp-item pp-item-blocker">
                <span className="pp-item-title">{b.title}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
