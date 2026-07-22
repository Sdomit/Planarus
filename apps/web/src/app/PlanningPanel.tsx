import { createContext, useContext, useEffect, useRef, useState } from 'react'
import {
  api, Blocker, ChecklistItem, Comment, Decision, Link, MemberRead, Milestone, Phase, Project, Risk, Stage, StatusOption, Task,
} from '../api/client'
import { StatusBadge, type ToneKind } from './StatusBadge'
import { InlineStatusSelect } from './InlineStatusSelect'
import { RowActions } from './RowActions'
import { EntityNotes } from './EntityNotes'
import { useListReorder } from './useListReorder'
import { EntityBoard, nextStatusForColumn as nextStatusForCol } from './EntityBoard'
import { StatusManager } from './StatusManager'
import { Markdown } from './markdown'
import { useAuthInfo } from './auth'
import './planning-panel.css'

// P16.3 (D33): team members (for the assignee picker) + the signed-in user id
// (for "assigned to me"). Empty/null in local mode, so the whole assignee UI is
// dormant — one provider at the panel root, consumers pull what they need
// without threading props through the recursive TaskRow tree.
const TeamContext = createContext<{ members: MemberRead[]; myId: string | null }>({
  members: [], myId: null,
})

// Phase 22 (D56): the project's comments + links, already loaded once at the
// panel root. Same reason as TeamContext — five different row types need them,
// and threading four props through every section→row signature to reach a
// collapsed detail body is worse than one provider. Rows filter by their own
// (entity_type, entity_id); writes push back here so the tabs stay in sync.
const AttachContext = createContext<{
  comments: Comment[]
  setComments: React.Dispatch<React.SetStateAction<Comment[]>>
  links: Link[]
  setLinks: React.Dispatch<React.SetStateAction<Link[]>>
} | null>(null)

/** Renders nothing outside a provider, so a row can mount it unconditionally. */
function Attachments({ entityType, entityId, projectId, label }: {
  entityType: string; entityId: string; projectId: string; label: string
}) {
  const ctx = useContext(AttachContext)
  if (!ctx) return null
  return (
    <EntityNotes projectId={projectId} entityType={entityType} entityId={entityId} label={label}
      comments={ctx.comments} setComments={ctx.setComments}
      links={ctx.links} setLinks={ctx.setLinks} />
  )
}

function personInitials(s: string): string {
  return (
    s.replace(/[^a-zA-Z0-9 ]/g, '').split(/\s+/).filter(Boolean).slice(0, 2)
      .map(w => w[0]).join('').toUpperCase() || '?'
  )
}

function personHue(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360
  return h
}

/** A compact assignee/author badge: colored initials + name. */
function PersonChip({ id, name }: { id: string; name: string }) {
  return (
    <span className="pp-person" title={name}>
      <span className="pp-person-dot" style={{ background: `hsl(${personHue(id)} 55% 42%)` }}>
        {personInitials(name)}
      </span>
      <span className="pp-person-name">{name}</span>
    </span>
  )
}

// Re-exported for tests + existing callers; the implementation now lives in EntityBoard.
export const nextStatusForColumn = nextStatusForCol

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
const COMMENT_STATUSES = ['active', 'done', 'attention']

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

// One-column-per-status board configs for the non-task entities.
const PHASE_DOT: Record<string, string> = {
  planned: 'var(--text-tertiary)', active: 'var(--status-info-fg)', blocked: 'var(--status-danger-fg)',
  done: 'var(--status-success-fg)', canceled: 'var(--text-tertiary)',
}
const MILESTONE_DOT: Record<string, string> = {
  planned: 'var(--text-tertiary)', active: 'var(--status-info-fg)', achieved: 'var(--status-success-fg)',
  missed: 'var(--status-danger-fg)', canceled: 'var(--text-tertiary)',
}
const DECISION_DOT: Record<string, string> = {
  proposed: 'var(--status-info-fg)', accepted: 'var(--status-success-fg)',
  superseded: 'var(--text-tertiary)', reversed: 'var(--status-danger-fg)',
}
const RISK_STATUS_DOT: Record<string, string> = {
  open: 'var(--status-danger-fg)', monitoring: 'var(--status-warning-fg)', mitigated: 'var(--status-success-fg)',
  accepted: 'var(--status-info-fg)', closed: 'var(--text-tertiary)',
}
const statusCols = (statuses: string[], dots: Record<string, string>): BoardCol[] =>
  statuses.map(s => ({ key: s, label: s.replace(/_/g, ' '), statuses: [s], dot: dots[s] ?? 'var(--text-tertiary)' }))
// All entity board columns are built dynamically from the project's status
// options (custom statuses); see PhasesSection / RisksSection.

/** Merge each custom status's stored color over the built-in dot palette, so
 *  board columns show the color chosen in the status manager. */
function statusDots(base: Record<string, string>, statuses?: StatusOption[]): Record<string, string> {
  const out = { ...base }
  for (const o of statuses ?? []) if (o.color) out[o.key] = o.color
  return out
}

/** A `key → custom color` lookup for `StatusBadge`/`InlineStatusSelect`. */
function colorMapOf(statuses?: StatusOption[]): (key: string) => string | undefined {
  const map = new Map<string, string>()
  for (const o of statuses ?? []) if (o.color) map.set(o.key, o.color)
  return key => map.get(key)
}

/** The "Manage statuses" button + its modal for one section. Enabled only when
 *  the section is wired with an entity type, badge kind, and a reload callback. */
function useStatusManager(opts: {
  projectId: string
  entityType?: string
  kind?: ToneKind
  statuses?: StatusOption[]
  reload?: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const enabled = !!(opts.entityType && opts.kind && opts.reload)
  const button = enabled ? (
    <button type="button" className="btn btn-outline btn-sm" onClick={() => setOpen(true)}>Manage statuses</button>
  ) : null
  const modal = open && enabled ? (
    <StatusManager
      projectId={opts.projectId} entityType={opts.entityType!} kind={opts.kind!}
      options={opts.statuses ?? []} onClose={() => setOpen(false)} onChanged={opts.reload!}
    />
  ) : null
  return { button, modal }
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
  const [taskStatuses, setTaskStatuses] = useState<StatusOption[]>([])
  const [phaseStatuses, setPhaseStatuses] = useState<StatusOption[]>([])
  const [riskStatuses, setRiskStatuses] = useState<StatusOption[]>([])
  const [milestoneStatuses, setMilestoneStatuses] = useState<StatusOption[]>([])
  const [decisionStatuses, setDecisionStatuses] = useState<StatusOption[]>([])
  const [milestones, setMilestones] = useState<Milestone[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [risks, setRisks] = useState<Risk[]>([])
  const [blockers, setBlockers] = useState<Blocker[]>([])
  const [comments, setComments] = useState<Comment[]>([])
  const [links, setLinks] = useState<Link[]>([])
  // P16.3: assignable people = the project workspace's members (team mode only).
  const { me } = useAuthInfo()
  const [members, setMembers] = useState<MemberRead[]>([])

  const [showCreate, setShowCreate] = useState(false)
  // Phase 22.1: which phase the type tabs are narrowed to. Set by clicking a
  // phase roll-up count; cleared by the chip. null = the whole project.
  const [phaseFilter, setPhaseFilter] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [phaseForm, setPhaseForm] = useState({ title: '', status: 'planned' })
  const [taskForm, setTaskForm] = useState({
    title: '', status: 'backlog', priority: '', phase_id: '', stage_id: '',
  })
  const [milestoneForm, setMilestoneForm] = useState({ title: '', status: 'planned', target_date: '', phase_id: '' })
  const [decisionForm, setDecisionForm] = useState({ title: '', decision: '', status: 'proposed', phase_id: '' })
  const [riskForm, setRiskForm] = useState({ title: '', severity: 'medium', status: 'open', phase_id: '' })
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

  // Load workspace members once we know the project + that we're in team mode.
  // 403/404 (not an owner, or auth off) → no picker, silently.
  useEffect(() => {
    if (!me || !project) { setMembers([]); return }
    let live = true
    api.members.list(project.workspace_id).then(
      m => { if (live) setMembers(m) },
      () => { if (live) setMembers([]) },
    )
    return () => { live = false }
  }, [me, project])

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
    const [ph, stg, tk, mil, dec, rsk, blk, cmt, lnk, sto, phSto, rkSto, mlSto, dcSto] = await Promise.all([
      api.phases.list(projectId),
      api.stages.list(projectId),
      api.tasks.list(projectId),
      api.milestones.list(projectId),
      api.decisions.list(projectId),
      api.risks.list(projectId),
      api.blockers.list(projectId),
      api.comments.list(projectId),
      api.links.list(projectId),
      api.statusOptions.list(projectId).catch(() => []),
      api.statusOptions.list(projectId, 'phase').catch(() => []),
      api.statusOptions.list(projectId, 'risk').catch(() => []),
      api.statusOptions.list(projectId, 'milestone').catch(() => []),
      api.statusOptions.list(projectId, 'decision').catch(() => []),
    ])
    setPhases(ph); setStages(stg); setTasks(tk); setMilestones(mil); setDecisions(dec)
    setRisks(rsk); setBlockers(blk); setComments(cmt); setLinks(lnk); setTaskStatuses(sto)
    setPhaseStatuses(phSto); setRiskStatuses(rkSto); setMilestoneStatuses(mlSto); setDecisionStatuses(dcSto)
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
        const mil = await api.milestones.create(project.id, {
          title: milestoneForm.title, status: milestoneForm.status,
          target_date: milestoneForm.target_date || undefined,
          phase_id: milestoneForm.phase_id || undefined,
        })
        setMilestones(prev => [...prev, mil]); setMilestoneForm({ title: '', status: 'planned', target_date: '', phase_id: '' })
      } else if (tab === 'decisions') {
        const dec = await api.decisions.create(project.id, {
          title: decisionForm.title, decision: decisionForm.decision, status: decisionForm.status,
          phase_id: decisionForm.phase_id || undefined,
        })
        setDecisions(prev => [dec, ...prev]); setDecisionForm({ title: '', decision: '', status: 'proposed', phase_id: '' })
      } else if (tab === 'risks') {
        const rsk = await api.risks.create(project.id, {
          title: riskForm.title, severity: riskForm.severity, status: riskForm.status,
          phase_id: riskForm.phase_id || undefined,
        })
        setRisks(prev => [...prev, rsk]); setRiskForm({ title: '', severity: 'medium', status: 'open', phase_id: '' })
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

  // Phase 22.1: narrow a type tab to one phase. Unphased rows drop out on
  // purpose — the filter answers "what is in this phase", and project-level
  // items are not in any phase.
  const inPhase = <T extends { phase_id: string | null }>(rows: T[]): T[] =>
    phaseFilter ? rows.filter(r => r.phase_id === phaseFilter) : rows
  const filteredPhase = phaseFilter ? phases.find(p => p.id === phaseFilter) : null

  // Blockers carry no phase_id — they reach a phase through their task. Without
  // this they ignored the filter entirely and project-wide blockers showed up
  // under "Showing <phase> only", which flatly contradicts the chip.
  const blockersInPhase = (rows: Blocker[]): Blocker[] => {
    if (!phaseFilter) return rows
    const taskPhase = new Map(tasks.map(t => [t.id, t.phase_id]))
    return rows.filter(b => b.task_id != null && taskPhase.get(b.task_id) === phaseFilter)
  }

  // Refresh one entity type's status options after the manager (or the quick
  // "+ Add status") mutates them.
  const reloadStatuses = {
    phase: async () => setPhaseStatuses(await api.statusOptions.list(project.id, 'phase')),
    task: async () => setTaskStatuses(await api.statusOptions.list(project.id, 'task')),
    milestone: async () => setMilestoneStatuses(await api.statusOptions.list(project.id, 'milestone')),
    decision: async () => setDecisionStatuses(await api.statusOptions.list(project.id, 'decision')),
    risk: async () => setRiskStatuses(await api.statusOptions.list(project.id, 'risk')),
  }
  const addStatusFor = (entityType: keyof typeof reloadStatuses) => async (label: string) => {
    await api.statusOptions.create(project.id, { entity_type: entityType, label })
    await reloadStatuses[entityType]()
  }

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
   <TeamContext.Provider value={{ members, myId: me?.user.id ?? null }}>
   <AttachContext.Provider value={{ comments, setComments, links, setLinks }}>
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
                  {(phaseStatuses.length ? phaseStatuses.map(o => o.key) : PHASE_STATUSES).map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
              </>
            )}
            {tab === 'tasks' && (
              <>
                <input className="input" required placeholder="Task title" aria-label="Task title"
                  value={taskForm.title} onChange={e => setTaskForm(f => ({ ...f, title: e.target.value }))} />
                <select className="input select" value={taskForm.status} aria-label="Task status"
                  onChange={e => setTaskForm(f => ({ ...f, status: e.target.value }))}>
                  {statusKeysOf(taskStatuses).map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
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
                <select className="input select" value={taskForm.stage_id} aria-label="Task sub-phase"
                  disabled={!taskForm.phase_id || taskStages.length === 0}
                  onChange={e => setTaskForm(f => ({ ...f, stage_id: e.target.value }))}>
                  <option value="">No sub-phase</option>
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
                  {(milestoneStatuses.length ? milestoneStatuses.map(o => o.key) : MILESTONE_STATUSES).map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
                <select className="input select" value={milestoneForm.phase_id} aria-label="Milestone phase"
                  onChange={e => setMilestoneForm(f => ({ ...f, phase_id: e.target.value }))}>
                  <option value="">No phase (project-wide)</option>
                  {phases.map(ph => <option key={ph.id} value={ph.id}>{ph.title}</option>)}
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
                  {(decisionStatuses.length ? decisionStatuses.map(o => o.key) : DECISION_STATUSES).map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
                <select className="input select" value={decisionForm.phase_id} aria-label="Decision phase"
                  onChange={e => setDecisionForm(f => ({ ...f, phase_id: e.target.value }))}>
                  <option value="">No phase (project-wide)</option>
                  {phases.map(ph => <option key={ph.id} value={ph.id}>{ph.title}</option>)}
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
                  {(riskStatuses.length ? riskStatuses.map(o => o.key) : RISK_STATUSES).map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
                <select className="input select" value={riskForm.phase_id} aria-label="Risk phase"
                  onChange={e => setRiskForm(f => ({ ...f, phase_id: e.target.value }))}>
                  <option value="">No phase (project-wide)</option>
                  {phases.map(ph => <option key={ph.id} value={ph.id}>{ph.title}</option>)}
                </select>
              </>
            )}
            {tab === 'comments' && (
              <textarea className="input" required placeholder="Add a comment on this project… (Markdown supported)" aria-label="Project comment"
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

        {filteredPhase && tab !== 'phases' && (
          <div className="pp-phase-filter">
            <span>Showing <strong>{filteredPhase.title}</strong> only</span>
            <button type="button" className="btn btn-ghost btn-xs"
              onClick={() => setPhaseFilter(null)}>Show all</button>
          </div>
        )}

        {tab === 'phases' && (
          <PhasesSection phases={phases} tasks={tasks} decisions={decisions} risks={risks}
            projectId={project.id} setPhases={setPhases}
            statuses={phaseStatuses} reloadStatuses={reloadStatuses.phase}
            addStatus={addStatusFor('phase')}
            onOpenInPhase={(nextTab, phaseId) => { setPhaseFilter(phaseId); setTab(nextTab) }}
            onAddInPhase={(nextTab, phaseId) => {
              setPhaseFilter(phaseId)
              setTab(nextTab)
              // Pre-fill the phase so the create form opens already scoped —
              // the whole point is not having to re-find the phase you were in.
              if (nextTab === 'tasks') setTaskForm(f => ({ ...f, phase_id: phaseId, stage_id: '' }))
              if (nextTab === 'milestones') setMilestoneForm(f => ({ ...f, phase_id: phaseId }))
              if (nextTab === 'decisions') setDecisionForm(f => ({ ...f, phase_id: phaseId }))
              if (nextTab === 'risks') setRiskForm(f => ({ ...f, phase_id: phaseId }))
              setShowCreate(true)
            }} />
        )}
        {tab === 'tasks' && (
          <TasksList tasks={inPhase(tasks)} phases={phases} stages={stages} projectId={project.id} setTasks={setTasks}
            taskStatuses={taskStatuses} reloadStatuses={reloadStatuses.task}
            addTaskStatus={addStatusFor('task')}
            onTaskUpdated={updated =>
              setTasks(prev => prev.map(task => task.id === updated.id ? updated : task))
            } />
        )}
        {tab === 'milestones' && (
          <MilestonesSection milestones={inPhase(milestones)} projectId={project.id} setMilestones={setMilestones}
            statuses={milestoneStatuses} reloadStatuses={reloadStatuses.milestone}
            addStatus={addStatusFor('milestone')} />
        )}
        {tab === 'decisions' && (
          <DecisionsSection decisions={inPhase(decisions)} phases={phases} projectId={project.id} setDecisions={setDecisions}
            statuses={decisionStatuses} reloadStatuses={reloadStatuses.decision}
            addStatus={addStatusFor('decision')} />
        )}
        {tab === 'risks' && (
          <RisksSection
            risks={inPhase(risks)}
            phases={phases}
            blockers={blockersInPhase(openBlockers)}
            projectId={project.id}
            setRisks={setRisks}
            statuses={riskStatuses} reloadStatuses={reloadStatuses.risk}
            addStatus={addStatusFor('risk')}
            onBlockerUpdated={updated => setBlockers(prev => prev.map(b => b.id === updated.id ? updated : b))}
          />
        )}
        {tab === 'comments' && <CommentsSection comments={comments} setComments={setComments} />}
        {tab === 'links' && <LinksList links={links} />}
      </div>
    </div>
   </AttachContext.Provider>
   </TeamContext.Provider>
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

/** View toggle shared by the entity sections. */
function ViewToggle({ view, setView }: { view: 'list' | 'board'; setView: (v: 'list' | 'board') => void }) {
  return (
    <div className="ab-seg" role="group" aria-label="View">
      <button type="button" aria-pressed={view === 'list'} className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button>
      <button type="button" aria-pressed={view === 'board'} className={view === 'board' ? 'active' : ''} onClick={() => setView('board')}>Board</button>
    </div>
  )
}

/** Inline title editor: the pencil (RowActions) calls `start`; Enter/blur saves. */
function useEditable(value: string, onSave: (next: string) => void) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const start = () => { setDraft(value); setEditing(true) }
  const node = editing ? (
    <input
      className="input input-sm pp-title-edit" autoFocus value={draft}
      onClick={e => e.stopPropagation()}
      onChange={e => setDraft(e.target.value)}
      onBlur={() => { setEditing(false); const t = draft.trim(); if (t && t !== value) onSave(t) }}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); setEditing(false); const t = draft.trim(); if (t && t !== value) onSave(t) }
        else if (e.key === 'Escape') { setEditing(false) }
      }}
    />
  ) : null
  return { editing, start, node }
}

/** Phase 19 (D45): what a phase rolls up, so a phase reads as a complete unit
 *  — "8/12 tasks · 2 decisions · 3 open risks" — instead of a bare title. */
export interface PhaseRollup {
  tasksDone: number
  tasksTotal: number
  decisions: number
  openRisks: number
}

const CLOSED_RISK_STATUSES = new Set(['mitigated', 'accepted', 'closed'])

export function phaseRollups(
  tasks: Task[], decisions: Decision[], risks: Risk[],
): Map<string, PhaseRollup> {
  const out = new Map<string, PhaseRollup>()
  const at = (id: string) => {
    let r = out.get(id)
    if (!r) { r = { tasksDone: 0, tasksTotal: 0, decisions: 0, openRisks: 0 }; out.set(id, r) }
    return r
  }
  for (const t of tasks) if (t.phase_id) { const r = at(t.phase_id); r.tasksTotal++; if (t.status === 'done') r.tasksDone++ }
  for (const d of decisions) if (d.phase_id) at(d.phase_id).decisions++
  for (const r of risks) if (r.phase_id && !CLOSED_RISK_STATUSES.has(r.status)) at(r.phase_id).openRisks++
  return out
}

/** Phase 22.1: the tabs a phase can send you to, pre-scoped to itself. */
export type PhaseScopedTab = 'tasks' | 'milestones' | 'decisions' | 'risks'

function PhasesSection({ phases, tasks = [], decisions = [], risks = [], projectId, setPhases, statuses, addStatus, reloadStatuses, onOpenInPhase, onAddInPhase }: {
  phases: Phase[]; projectId: string; setPhases: React.Dispatch<React.SetStateAction<Phase[]>>
  tasks?: Task[]; decisions?: Decision[]; risks?: Risk[]
  statuses?: StatusOption[]; addStatus?: (label: string) => Promise<void>; reloadStatuses?: () => Promise<void>
  onOpenInPhase?: (tab: PhaseScopedTab, phaseId: string) => void
  onAddInPhase?: (tab: PhaseScopedTab, phaseId: string) => void
}) {
  const rollups = phaseRollups(tasks, decisions, risks)
  const [view, setView] = useState<'list' | 'board'>('list')
  const statusKeys = statuses && statuses.length ? statuses.map(o => o.key) : PHASE_STATUSES
  const onAddNew = addStatus ? () => promptNewStatus(addStatus) : undefined
  const colorOf = colorMapOf(statuses)
  const mgr = useStatusManager({ projectId, entityType: 'phase', kind: 'phase', statuses, reload: reloadStatuses })
  const onUpdated = (u: Phase) => setPhases(prev => prev.map(p => (p.id === u.id ? u : p)))
  const onDeleted = (id: string) => setPhases(prev => prev.filter(p => p.id !== id))
  const update = (id: string, patch: Parameters<typeof api.phases.update>[1]) => void api.phases.update(id, patch).then(onUpdated)
  const remove = (id: string) => void api.phases.remove(id).then(() => onDeleted(id))
  const { itemProps, reorder, moveBy } = useListReorder(phases, next => setPhases(next), ids => api.phases.reorder(projectId, ids))

  if (phases.length === 0)
    return <><div className="pp-toolbar">{mgr.button}</div><p style={EMPTY}>No phases yet.</p>{mgr.modal}</>

  return (
    <>
      <div className="pp-toolbar"><ViewToggle view={view} setView={setView} />{mgr.button}</div>
      {view === 'board' ? (
        <EntityBoard
          labelOf={p => p.title} items={phases} columns={statusCols(statusKeys, statusDots(PHASE_DOT, statuses))} statusOf={p => p.status}
          onRestatus={(p, status) => update(p.id, { status })}
          onReorder={reorder}
          onAddColumn={onAddNew}
          renderCard={p => (
            <div className="ab-task-foot" style={{ justifyContent: 'space-between' }}>
              <span className="ab-task-title">{p.title}</span>
              <RowActions title={p.title} onDelete={() => remove(p.id)} />
            </div>
          )}
        />
      ) : (
        <ul className="pp-rows">
          {phases.map(ph => (
            <PhaseListRow key={ph.id} phase={ph} rollup={rollups.get(ph.id)} update={update} remove={remove} dragProps={itemProps(ph.id)} move={delta => void moveBy(ph.id, delta)}
              statusKeys={statusKeys} onAddNew={onAddNew} colorOf={colorOf}
              onOpenInPhase={onOpenInPhase} onAddInPhase={onAddInPhase} />
          ))}
        </ul>
      )}
      {mgr.modal}
    </>
  )
}

function PhaseListRow({ phase, rollup, update, remove, dragProps, move, statusKeys = PHASE_STATUSES, onAddNew, colorOf, onOpenInPhase, onAddInPhase }: {
  phase: Phase
  rollup?: PhaseRollup
  onOpenInPhase?: (tab: PhaseScopedTab, phaseId: string) => void
  onAddInPhase?: (tab: PhaseScopedTab, phaseId: string) => void
  update: (id: string, patch: Parameters<typeof api.phases.update>[1]) => void
  statusKeys?: string[]
  onAddNew?: () => void
  colorOf?: (key: string) => string | undefined
  remove: (id: string) => void
  dragProps: React.HTMLAttributes<HTMLLIElement> & { draggable?: boolean }
  /** Touch/keyboard reorder — dragging is mouse-only. */
  move?: (delta: -1 | 1) => void
}) {
  const [open, setOpen] = useState(false)
  const editable = useEditable(phase.title, t => update(phase.id, { title: t }))
  return (
    <li className="pp-row pp-row-expandable pp-row-managed" {...dragProps}>
      <div className="pp-row-main-wrap">
        <button type="button" className="pp-row-main" onClick={() => setOpen(v => !v)} aria-expanded={open}>
          <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {editable.node ?? <span className="pp-row-title">{phase.title}</span>}
        </button>
        {rollup && <PhaseRollupChips rollup={rollup} phaseId={phase.id} onOpenInPhase={onOpenInPhase} />}
        <InlineStatusSelect kind="phase" value={phase.status} options={statusKeys}
          onChange={s => update(phase.id, { status: s })} label={`Change status of ${phase.title}`} onAddNew={onAddNew} colorOf={colorOf} />
        <RowActions title={phase.title} onEdit={editable.start} onDelete={() => remove(phase.id)} dragHandle
          onMoveUp={move && (() => move(-1))} onMoveDown={move && (() => move(1))} />
      </div>
      {open && (
        <div className="pp-task-details">
          {phase.description && <p className="pp-row-desc">{phase.description}</p>}
          {onAddInPhase && (
            <div className="pp-phase-add" role="group" aria-label={`Add to ${phase.title}`}>
              {(['tasks', 'milestones', 'decisions', 'risks'] as PhaseScopedTab[]).map(t => (
                <button key={t} type="button" className="btn btn-outline btn-xs"
                  onClick={() => onAddInPhase(t, phase.id)}>
                  Add {t.replace(/s$/, '')} here
                </button>
              ))}
            </div>
          )}
          <Attachments entityType="phase" entityId={phase.id} projectId={phase.project_id} label={phase.title} />
        </div>
      )}
    </li>
  )
}

/** The phase's contents at a glance. Zero-valued parts are omitted rather than
 *  shown as "0", so a phase only carries the signal it actually has. */
function PhaseRollupChips({ rollup, phaseId, onOpenInPhase }: {
  rollup: PhaseRollup
  phaseId?: string
  onOpenInPhase?: (tab: PhaseScopedTab, phaseId: string) => void
}) {
  const parts: { tab: PhaseScopedTab; text: string }[] = []
  if (rollup.tasksTotal) parts.push({ tab: 'tasks', text: `${rollup.tasksDone}/${rollup.tasksTotal} tasks` })
  if (rollup.decisions) parts.push({ tab: 'decisions', text: `${rollup.decisions} decision${rollup.decisions === 1 ? '' : 's'}` })
  if (rollup.openRisks) parts.push({ tab: 'risks', text: `${rollup.openRisks} open risk${rollup.openRisks === 1 ? '' : 's'}` })
  if (!parts.length) return null

  // Phase 22.1: each count opens its tab narrowed to this phase. Without a
  // handler it stays plain text — a count that looks clickable but isn't is
  // worse than one that doesn't.
  if (!onOpenInPhase || !phaseId) {
    return <span className="pp-card-phase">{parts.map(p => p.text).join(' · ')}</span>
  }
  return (
    <span className="pp-card-phase pp-rollup">
      {parts.map((p, i) => (
        <span key={p.tab}>
          {i > 0 && <span aria-hidden="true"> · </span>}
          <button type="button" className="pp-rollup-link"
            onClick={e => { e.stopPropagation(); onOpenInPhase(p.tab, phaseId) }}>
            {p.text}
          </button>
        </span>
      ))}
    </span>
  )
}

/** Phase 19: which phase an item belongs to. Renders nothing when unphased —
 *  a project-wide decision/risk is a valid shape, not a missing value. */
function PhaseChip({ phaseId, phases }: { phaseId: string | null; phases: Phase[] }) {
  if (!phaseId) return null
  const title = phases.find(p => p.id === phaseId)?.title
  if (!title) return null
  return <span className="pp-card-phase">{title}</span>
}

/** Re-assign (or clear) an item's phase. '' maps to null, not undefined, so
 *  clearing actually sends the field instead of omitting it from the PATCH. */
function PhasePicker({ phaseId, phases, label, onChange }: {
  phaseId: string | null; phases: Phase[]; label: string
  onChange: (phaseId: string | null) => void
}) {
  if (phases.length === 0) return null
  return (
    <select className="input select input-sm" aria-label={label} value={phaseId ?? ''}
      onChange={e => onChange(e.target.value || null)}>
      <option value="">No phase (project-wide)</option>
      {phases.map(ph => <option key={ph.id} value={ph.id}>{ph.title}</option>)}
    </select>
  )
}

interface TasksListProps {
  tasks: Task[]
  phases: Phase[]
  stages: Stage[]
  projectId: string
  onTaskUpdated: (task: Task) => void
  setTasks?: React.Dispatch<React.SetStateAction<Task[]>>
  taskStatuses?: StatusOption[]
  addTaskStatus?: (label: string) => Promise<void>
  reloadStatuses?: () => Promise<void>
}

/** The task status keys in effect — the project's options (built-in ∪ custom)
 *  when loaded, else the canonical fallback. */
function statusKeysOf(taskStatuses?: StatusOption[]): string[] {
  return taskStatuses && taskStatuses.length ? taskStatuses.map(o => o.key) : TASK_STATUSES
}

/** Prompt for a new status name and create it (the server slugifies the key). */
function promptNewStatus(add: (label: string) => Promise<void>): void {
  const label = window.prompt('New status name (e.g. "In Review")')?.trim()
  if (label) void add(label)
}

function TasksList({ tasks, phases, stages, projectId, onTaskUpdated, setTasks, taskStatuses, addTaskStatus, reloadStatuses }: TasksListProps) {
  const statusKeys = statusKeysOf(taskStatuses)
  const colorOf = colorMapOf(taskStatuses)
  const mgr = useStatusManager({ projectId, entityType: 'task', kind: 'task', statuses: taskStatuses, reload: reloadStatuses })
  const LIST_FILTERS = ['open', 'all', ...statusKeys]
  const [view, setView] = useState<'list' | 'board'>('list')
  const [filter, setFilter] = useState('open')
  const [mineOnly, setMineOnly] = useState(false)
  const { myId } = useContext(TeamContext)  // P16.3: "assigned to me" (team mode)
  const done = tasks.filter(t => t.status === 'done' || t.status === 'canceled').length
  const remove = (id: string) => void api.tasks.remove(id).then(() => setTasks?.(prev => prev.filter(t => t.id !== id)))
  // Reorder operates on the FULL task list (both drag + target are always in it),
  // so it stays valid even while a filter narrows the visible rows.
  const { itemProps, moveBy } = useListReorder(tasks, next => setTasks?.(next), ids => api.tasks.reorder(projectId, ids))

  if (tasks.length === 0)
    return <><div className="pp-toolbar">{mgr.button}</div><p style={EMPTY}>No tasks yet.</p>{mgr.modal}</>

  const shown = tasks.filter(t => {
    if (mineOnly && t.assignee_id !== myId) return false
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
          {myId && (
            <label className="pp-mine-filter">
              <input type="checkbox" checked={mineOnly} onChange={e => setMineOnly(e.target.checked)} />
              <span>Assigned to me</span>
            </label>
          )}
          {mgr.button}
        </div>
        {done > 0 && <span className="pp-done-lbl">{done} done</span>}
      </div>
      {mgr.modal}

      {view === 'board' ? (
        <TaskBoard tasks={tasks} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated}
          setTasks={setTasks} taskStatuses={taskStatuses} addTaskStatus={addTaskStatus} />
      ) : shown.length === 0 ? (
        <p style={EMPTY}>No tasks match this filter.</p>
      ) : (() => {
        // Group sub-tasks under their parent (one level); orphans (parent filtered
        // out) render at top level so nothing is hidden.
        const childrenOf = new Map<string, Task[]>()
        const shownIds = new Set(shown.map(t => t.id))
        const top: Task[] = []
        for (const t of shown) {
          if (t.parent_task_id && shownIds.has(t.parent_task_id)) {
            const arr = childrenOf.get(t.parent_task_id) ?? []
            arr.push(t); childrenOf.set(t.parent_task_id, arr)
          } else {
            top.push(t)
          }
        }
        return (
          <ul className="pp-rows">
            {top.map(t => (
              <TaskRow key={t.id} task={t} phases={phases} stages={stages} projectId={projectId}
                onTaskUpdated={onTaskUpdated} onDelete={setTasks ? () => remove(t.id) : undefined}
                dragProps={setTasks && !t.parent_task_id ? itemProps(t.id) : undefined}
                move={setTasks && !t.parent_task_id ? delta => void moveBy(t.id, delta) : undefined}
                subtasks={childrenOf.get(t.id) ?? []} setTasks={setTasks}
                statusKeys={statusKeys} addTaskStatus={addTaskStatus} colorOf={colorOf} />
            ))}
          </ul>
        )
      })()}
    </>
  )
}

/** Kanban board with two groupings (Flow buckets / per-status), drag-to-restatus, and click-to-open. */
function TaskBoard({ tasks, phases, stages, projectId, onTaskUpdated, setTasks, taskStatuses, addTaskStatus }: TasksListProps) {
  const [group, setGroup] = useState<'flow' | 'status'>('flow')
  const [openId, setOpenId] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [overCol, setOverCol] = useState<string | null>(null)
  const statusKeys = statusKeysOf(taskStatuses)
  // Status grouping: one column per status (built-in + custom). Flow: fixed buckets.
  const cols = group === 'flow' ? BOARD_COLS : statusCols(statusKeys, statusDots(STATUS_DOT, taskStatuses))
  const phaseTitle = new Map(phases.map(phase => [phase.id, phase.title]))
  const openTask = tasks.find(t => t.id === openId) ?? null
  const { reorder } = useListReorder(tasks, next => setTasks?.(next), ids => api.tasks.reorder(projectId, ids))

  async function restatus(id: string, status: string) {
    try {
      onTaskUpdated(await api.tasks.update(id, { status }))
    } catch {
      /* leave the card where it was on failure */
    }
  }

  async function dropOn(col: BoardCol) {
    setOverCol(null)
    const id = dragId
    setDragId(null)
    if (!id) return
    const task = tasks.find(t => t.id === id)
    if (!task) return
    const status = nextStatusForColumn(task.status, col)
    if (status) await restatus(id, status)
  }

  function dropOnCard(targetId: string) {
    const id = dragId
    setOverCol(null)
    setDragId(null)
    if (!id || id === targetId) return
    const dragTask = tasks.find(t => t.id === id)
    const targetTask = tasks.find(t => t.id === targetId)
    if (!dragTask || !targetTask) return
    if (dragTask.status === targetTask.status) reorder(id, targetId)
    else void restatus(id, targetTask.status)
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
                    onDragOver={e => { e.preventDefault(); e.stopPropagation() }}
                    onDrop={e => { e.preventDefault(); e.stopPropagation(); dropOnCard(t.id) }}
                    onClick={() => setOpenId(t.id)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); setOpenId(t.id) } }}
                  >
                    <div className="ab-task-title">{t.title}</div>
                    <div className="ab-task-foot">
                      {t.phase_id && <span className="pp-card-phase">{phaseTitle.get(t.phase_id)}</span>}
                      <StatusBadge kind="task" value={t.status} />
                      {setTasks && <RowActions title={t.title} onDelete={() => void api.tasks.remove(t.id).then(() => setTasks(prev => prev.filter(x => x.id !== t.id)))} />}
                    </div>
                  </div>
                ))}
              </div>
            )
          })}
          {group === 'status' && addTaskStatus && (
            <div className="ab-col ab-col-add">
              <button type="button" className="ab-col-add-btn" onClick={() => promptNewStatus(addTaskStatus)}>
                + Add column
              </button>
            </div>
          )}
        </div>
      </div>
      {openTask && (
        <TaskDialog task={openTask} phases={phases} stages={stages} projectId={projectId} statusKeys={statusKeys}
          onClose={() => setOpenId(null)} onTaskUpdated={onTaskUpdated} />
      )}
    </>
  )
}

/** Card detail as a native modal dialog (Esc / backdrop / ✕ all close it). */
function TaskDialog({ task, phases, stages, projectId, onClose, onTaskUpdated, statusKeys }: {
  task: Task; phases: Phase[]; stages: Stage[]; projectId: string
  onClose: () => void; onTaskUpdated: (task: Task) => void; statusKeys?: string[]
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
      <TaskDetailBody task={task} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated} statusKeys={statusKeys} />
    </dialog>
  )
}

/** Shared task detail: status/priority/phase/stage controls, checklist, and comments. */
function TaskDetailBody({ task, phases, stages, projectId, onTaskUpdated, statusKeys = TASK_STATUSES }: {
  task: Task; phases: Phase[]; stages: Stage[]; projectId: string; onTaskUpdated: (task: Task) => void
  statusKeys?: string[]
}) {
  const [items, setItems] = useState<ChecklistItem[]>([])
  const [label, setLabel] = useState('')
  const [saving, setSaving] = useState(false)
  const [taskError, setTaskError] = useState<string | null>(null)
  const [checklistError, setChecklistError] = useState<string | null>(null)
  const { members } = useContext(TeamContext)  // P16.3: assignee options (team mode)
  const taskStages = task.phase_id ? stages.filter(stage => stage.phase_id === task.phase_id) : []

  useEffect(() => { void api.checklistItems.list(task.id).then(setItems) }, [task.id])

  async function addItem(e: React.FormEvent) {
    e.preventDefault()
    if (!label.trim()) return
    setChecklistError(null)
    try {
      const item = await api.checklistItems.create(task.id, { label: label.trim() })
      setItems(prev => [...prev, item]); setLabel('')
    } catch (error) {
      setChecklistError(error instanceof Error ? error.message : String(error))
    }
  }

  async function toggleDone(item: ChecklistItem) {
    setChecklistError(null)
    try {
      const updated = await api.checklistItems.update(item.id, { done: !item.done })
      setItems(prev => prev.map(i => (i.id === updated.id ? updated : i)))
    } catch (error) {
      setChecklistError(error instanceof Error ? error.message : String(error))
    }
  }

  async function removeItem(item: ChecklistItem) {
    setChecklistError(null)
    try {
      await api.checklistItems.remove(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
    } catch (error) {
      setChecklistError(error instanceof Error ? error.message : String(error))
    }
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
            {statusKeys.map(status => <option key={status} value={status}>{status.replace(/_/g, ' ')}</option>)}
          </select>
        </label>
        <label>
          <span>Priority</span>
          <select className="input select input-sm" value={task.priority ?? ''} disabled={saving}
            onChange={event => void updateTask({ priority: event.target.value || null })}>
            {TASK_PRIORITIES.map(priority => <option key={priority || 'none'} value={priority}>{priority || 'none'}</option>)}
          </select>
        </label>
        {members.length > 0 && (
          <label>
            <span>Assignee</span>
            <select className="input select input-sm" value={task.assignee_id ?? ''} disabled={saving}
              aria-label={`Assignee for ${task.title}`}
              onChange={event => void updateTask({ assignee_id: event.target.value || null })}>
              <option value="">Unassigned</option>
              {members.map(m => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
            </select>
          </label>
        )}
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
          <span>Sub-phase</span>
          <select className="input select input-sm" value={task.stage_id ?? ''}
            disabled={saving || !task.phase_id || taskStages.length === 0}
            onChange={event => void updateTask({ stage_id: event.target.value || null })}>
            <option value="">No sub-phase</option>
            {taskStages.map(stage => <option key={stage.id} value={stage.id}>{stage.title}</option>)}
          </select>
        </label>
      </div>
      {taskError && <p className="form-error" role="alert">{taskError}</p>}
      <div className="pp-checklist">
        {items.map(i => (
          <div key={i.id} className="pp-check-row">
            <label className="pp-check">
              <input type="checkbox" checked={i.done} onChange={() => toggleDone(i)} />
              <span className={i.done ? 'pp-check-done' : ''}>{i.label}</span>
            </label>
            <button type="button" className="pp-check-remove" aria-label={`Remove ${i.label}`}
              onClick={() => removeItem(i)}>×</button>
          </div>
        ))}
        {checklistError && <p className="form-error" role="alert">{checklistError}</p>}
        <form className="pp-check-add" onSubmit={addItem}>
          <input className="input" placeholder="Add checklist item…" aria-label={`Add checklist item to ${task.title}`}
            value={label} onChange={e => setLabel(e.target.value)} />
          <button type="submit" className="btn btn-outline btn-sm">Add</button>
        </form>
      </div>
      <Attachments entityType="task" entityId={task.id} projectId={projectId} label={task.title} />
    </div>
  )
}


/** A task row: inline status/title edit + delete/drag in the header, expands to
 *  the shared task detail; renders its sub-tasks nested beneath. */
function TaskRow({ task, phases, stages, projectId, onTaskUpdated, onDelete, dragProps, move, subtasks = [], setTasks, statusKeys = TASK_STATUSES, addTaskStatus, colorOf }: {
  task: Task; phases: Phase[]; stages: Stage[]; projectId: string; onTaskUpdated: (task: Task) => void
  onDelete?: () => void
  dragProps?: React.HTMLAttributes<HTMLLIElement> & { draggable?: boolean }
  /** Touch/keyboard reorder — dragging is mouse-only. */
  move?: (delta: -1 | 1) => void
  subtasks?: Task[]
  setTasks?: React.Dispatch<React.SetStateAction<Task[]>>
  statusKeys?: string[]
  addTaskStatus?: (label: string) => Promise<void>
  colorOf?: (key: string) => string | undefined
}) {
  const [open, setOpen] = useState(false)
  const [addingSub, setAddingSub] = useState(false)
  const [subTitle, setSubTitle] = useState('')
  const isSub = Boolean(task.parent_task_id)
  const update = (patch: Parameters<typeof api.tasks.update>[1]) => void api.tasks.update(task.id, patch).then(onTaskUpdated)
  const editable = useEditable(task.title, t => update({ title: t }))
  const onAddNew = addTaskStatus ? () => promptNewStatus(addTaskStatus) : undefined

  async function addSubtask(e: React.FormEvent) {
    e.preventDefault()
    if (!subTitle.trim() || !setTasks) return
    const created = await api.tasks.create(projectId, { title: subTitle.trim(), parent_task_id: task.id })
    setTasks(prev => [...prev, created]); setSubTitle(''); setAddingSub(false)
  }

  return (
    <li className={`pp-row pp-row-expandable pp-row-managed${isSub ? ' pp-row-subtask' : ''}`} {...dragProps}>
      <div className="pp-row-main-wrap">
        <button
          type="button"
          className="pp-row-main"
          onClick={() => setOpen(v => !v)}
          aria-expanded={open}
          aria-controls={`task-details-${task.id}`}
        >
          <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {editable.node ?? <span className="pp-row-title">{task.title}</span>}
          {subtasks.length > 0 && <span className="pp-subcount">{subtasks.length}</span>}
          {task.assignee_id && task.assignee_display && (
            <PersonChip id={task.assignee_id} name={task.assignee_display} />
          )}
        </button>
        <InlineStatusSelect kind="task" value={task.status} options={statusKeys}
          onChange={s => update({ status: s })} label={`Change status of ${task.title}`} onAddNew={onAddNew} colorOf={colorOf} />
        <RowActions title={task.title} onEdit={editable.start} onDelete={onDelete} dragHandle={Boolean(dragProps)}
          onMoveUp={move && (() => move(-1))} onMoveDown={move && (() => move(1))} />
      </div>
      {open && <TaskDetailBody task={task} phases={phases} stages={stages} projectId={projectId} onTaskUpdated={onTaskUpdated} statusKeys={statusKeys} />}
      {(subtasks.length > 0 || (setTasks && !isSub)) && (
        <div className="pp-subtasks">
          <ul className="pp-rows">
            {subtasks.map(st => (
              <TaskRow key={st.id} task={st} phases={phases} stages={stages} projectId={projectId}
                onTaskUpdated={onTaskUpdated} statusKeys={statusKeys} addTaskStatus={addTaskStatus} colorOf={colorOf}
                onDelete={setTasks ? () => void api.tasks.remove(st.id).then(() => setTasks(prev => prev.filter(x => x.id !== st.id))) : undefined} />
            ))}
          </ul>
          {setTasks && !isSub && (
            addingSub ? (
              <form className="pp-check-add" onSubmit={addSubtask}>
                <input className="input input-sm" autoFocus placeholder="Sub-task title…" aria-label={`Add sub-task to ${task.title}`}
                  value={subTitle} onChange={e => setSubTitle(e.target.value)} onBlur={() => { if (!subTitle.trim()) setAddingSub(false) }} />
                <button type="submit" className="btn btn-outline btn-sm">Add</button>
              </form>
            ) : (
              <button type="button" className="pp-row-act pp-add-sub" onClick={() => setAddingSub(true)}>+ Sub-task</button>
            )
          )}
        </div>
      )}
    </li>
  )
}

function MilestonesSection({ milestones, projectId, setMilestones, statuses, addStatus, reloadStatuses }: {
  milestones: Milestone[]; projectId: string; setMilestones: React.Dispatch<React.SetStateAction<Milestone[]>>
  statuses?: StatusOption[]; addStatus?: (label: string) => Promise<void>; reloadStatuses?: () => Promise<void>
}) {
  const [view, setView] = useState<'list' | 'board'>('list')
  const statusKeys = statuses && statuses.length ? statuses.map(o => o.key) : MILESTONE_STATUSES
  const onAddNew = addStatus ? () => promptNewStatus(addStatus) : undefined
  const colorOf = colorMapOf(statuses)
  const mgr = useStatusManager({ projectId, entityType: 'milestone', kind: 'milestone', statuses, reload: reloadStatuses })
  const onUpdated = (u: Milestone) => setMilestones(prev => prev.map(m => (m.id === u.id ? u : m)))
  const update = (id: string, patch: Parameters<typeof api.milestones.update>[1]) => void api.milestones.update(id, patch).then(onUpdated)
  const remove = (id: string) => void api.milestones.remove(id).then(() => setMilestones(prev => prev.filter(m => m.id !== id)))
  const { itemProps, reorder, moveBy } = useListReorder(milestones, next => setMilestones(next), ids => api.milestones.reorder(projectId, ids))

  if (milestones.length === 0)
    return <><div className="pp-toolbar">{mgr.button}</div><p style={EMPTY}>No milestones yet.</p>{mgr.modal}</>

  return (
    <>
      <div className="pp-toolbar"><ViewToggle view={view} setView={setView} />{mgr.button}</div>
      {view === 'board' ? (
        <EntityBoard
          labelOf={m => m.title} items={milestones} columns={statusCols(statusKeys, statusDots(MILESTONE_DOT, statuses))} statusOf={m => m.status}
          onRestatus={(m, status) => update(m.id, { status })}
          onReorder={reorder}
          onAddColumn={onAddNew}
          renderCard={m => (
            <div className="ab-task-foot" style={{ justifyContent: 'space-between' }}>
              <span className="ab-task-title">{m.title}</span>
              <RowActions title={m.title} onDelete={() => remove(m.id)} />
            </div>
          )}
        />
      ) : (
        <ul className="pp-rows">
          {milestones.map(m => (
            <MilestoneListRow key={m.id} milestone={m} update={update} remove={remove} dragProps={itemProps(m.id)} move={delta => void moveBy(m.id, delta)}
              statusKeys={statusKeys} onAddNew={onAddNew} colorOf={colorOf} />
          ))}
        </ul>
      )}
      {mgr.modal}
    </>
  )
}

function MilestoneListRow({ milestone, update, remove, dragProps, move, statusKeys = MILESTONE_STATUSES, onAddNew, colorOf }: {
  milestone: Milestone
  update: (id: string, patch: Parameters<typeof api.milestones.update>[1]) => void
  remove: (id: string) => void
  dragProps: React.HTMLAttributes<HTMLLIElement> & { draggable?: boolean }
  /** Touch/keyboard reorder — dragging is mouse-only. */
  move?: (delta: -1 | 1) => void
  statusKeys?: string[]
  onAddNew?: () => void
  colorOf?: (key: string) => string | undefined
}) {
  const [open, setOpen] = useState(false)
  const editable = useEditable(milestone.title, t => update(milestone.id, { title: t }))
  return (
    <li className="pp-row pp-row-expandable pp-row-managed" {...dragProps}>
      <div className="pp-row-main-wrap">
        <button type="button" className="pp-row-main" onClick={() => setOpen(v => !v)} aria-expanded={open}>
          <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {editable.node ?? <span className="pp-row-title">{milestone.title}</span>}
          {milestone.target_date && <span className="pp-meta">{milestone.target_date}</span>}
        </button>
        <InlineStatusSelect kind="milestone" value={milestone.status} options={statusKeys}
          onChange={s => update(milestone.id, { status: s })} label={`Change status of ${milestone.title}`} onAddNew={onAddNew} colorOf={colorOf} />
        <RowActions title={milestone.title} onEdit={editable.start} onDelete={() => remove(milestone.id)} dragHandle
          onMoveUp={move && (() => move(-1))} onMoveDown={move && (() => move(1))} />
      </div>
      {open && (
        <div className="pp-task-details">
          {milestone.description && <p className="pp-row-desc">{milestone.description}</p>}
          <div className="pp-task-controls" role="group" aria-label={`Edit ${milestone.title}`}>
            <label>
              <span>Target date</span>
              <input type="date" className="input input-sm" value={milestone.target_date ?? ''}
                onChange={e => update(milestone.id, { target_date: e.target.value || null })} />
            </label>
          </div>
          <Attachments entityType="milestone" entityId={milestone.id} projectId={milestone.project_id} label={milestone.title} />
        </div>
      )}
    </li>
  )
}

function DecisionsSection({ decisions, phases = [], projectId, setDecisions, statuses, addStatus, reloadStatuses }: {
  decisions: Decision[]; phases?: Phase[]; projectId: string; setDecisions: React.Dispatch<React.SetStateAction<Decision[]>>
  statuses?: StatusOption[]; addStatus?: (label: string) => Promise<void>; reloadStatuses?: () => Promise<void>
}) {
  const [view, setView] = useState<'list' | 'board'>('list')
  const statusKeys = statuses && statuses.length ? statuses.map(o => o.key) : DECISION_STATUSES
  const onAddNew = addStatus ? () => promptNewStatus(addStatus) : undefined
  const colorOf = colorMapOf(statuses)
  const mgr = useStatusManager({ projectId, entityType: 'decision', kind: 'decision', statuses, reload: reloadStatuses })
  const onUpdated = (u: Decision) => setDecisions(prev => prev.map(d => (d.id === u.id ? u : d)))
  const update = (id: string, patch: Parameters<typeof api.decisions.update>[1]) => void api.decisions.update(id, patch).then(onUpdated)
  const remove = (id: string) => void api.decisions.remove(id).then(() => setDecisions(prev => prev.filter(d => d.id !== id)))
  const { itemProps, reorder, moveBy } = useListReorder(decisions, next => setDecisions(next), ids => api.decisions.reorder(projectId, ids))

  if (decisions.length === 0)
    return <><div className="pp-toolbar">{mgr.button}</div><p style={EMPTY}>No decisions yet.</p>{mgr.modal}</>

  return (
    <>
      <div className="pp-toolbar"><ViewToggle view={view} setView={setView} />{mgr.button}</div>
      {view === 'board' ? (
        <EntityBoard
          labelOf={d => d.title} items={decisions} columns={statusCols(statusKeys, statusDots(DECISION_DOT, statuses))} statusOf={d => d.status}
          onRestatus={(d, status) => update(d.id, { status })}
          onReorder={reorder}
          onAddColumn={onAddNew}
          renderCard={d => (
            <div className="ab-task-foot" style={{ justifyContent: 'space-between' }}>
              <span className="ab-task-title">{d.title}</span>
              <RowActions title={d.title} onDelete={() => remove(d.id)} />
            </div>
          )}
        />
      ) : (
        <ul className="pp-rows">
          {decisions.map(d => (
            <DecisionListRow key={d.id} decision={d} phases={phases} update={update} remove={remove} dragProps={itemProps(d.id)} move={delta => void moveBy(d.id, delta)}
              statusKeys={statusKeys} onAddNew={onAddNew} colorOf={colorOf} />
          ))}
        </ul>
      )}
      {mgr.modal}
    </>
  )
}

function DecisionListRow({ decision, phases = [], update, remove, dragProps, move, statusKeys = DECISION_STATUSES, onAddNew, colorOf }: {
  decision: Decision
  phases?: Phase[]
  update: (id: string, patch: Parameters<typeof api.decisions.update>[1]) => void
  remove: (id: string) => void
  dragProps: React.HTMLAttributes<HTMLLIElement> & { draggable?: boolean }
  /** Touch/keyboard reorder — dragging is mouse-only. */
  move?: (delta: -1 | 1) => void
  statusKeys?: string[]
  onAddNew?: () => void
  colorOf?: (key: string) => string | undefined
}) {
  const [open, setOpen] = useState(false)
  const editable = useEditable(decision.title, t => update(decision.id, { title: t }))
  return (
    <li className="pp-row pp-row-expandable pp-row-managed" {...dragProps}>
      <div className="pp-row-main-wrap">
        <button type="button" className="pp-row-main" onClick={() => setOpen(v => !v)} aria-expanded={open}>
          <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {editable.node ?? <span className="pp-row-title">{decision.title}</span>}
        </button>
        <PhaseChip phaseId={decision.phase_id} phases={phases} />
        <InlineStatusSelect kind="decision" value={decision.status} options={statusKeys}
          onChange={s => update(decision.id, { status: s })} label={`Change status of ${decision.title}`} onAddNew={onAddNew} colorOf={colorOf} />
        <RowActions title={decision.title} onEdit={editable.start} onDelete={() => remove(decision.id)} dragHandle
          onMoveUp={move && (() => move(-1))} onMoveDown={move && (() => move(1))} />
      </div>
      {open && (
        <div className="pp-task-details">
          <p className="pp-row-desc">{decision.decision}</p>
          {decision.context && <p className="pp-row-desc">{decision.context}</p>}
          <PhasePicker phaseId={decision.phase_id} phases={phases} label={`Phase for ${decision.title}`}
            onChange={phase_id => update(decision.id, { phase_id })} />
          <Attachments entityType="decision" entityId={decision.id} projectId={decision.project_id} label={decision.title} />
        </div>
      )}
    </li>
  )
}

function RisksSection({
  risks, phases = [], blockers, projectId, setRisks, onBlockerUpdated, statuses, addStatus, reloadStatuses,
}: {
  risks: Risk[]; phases?: Phase[]; blockers: Blocker[]; projectId: string
  setRisks: React.Dispatch<React.SetStateAction<Risk[]>>; onBlockerUpdated: (b: Blocker) => void
  statuses?: StatusOption[]; addStatus?: (label: string) => Promise<void>; reloadStatuses?: () => Promise<void>
}) {
  const [view, setView] = useState<'list' | 'board'>('list')
  const statusKeys = statuses && statuses.length ? statuses.map(o => o.key) : RISK_STATUSES
  const onAddNew = addStatus ? () => promptNewStatus(addStatus) : undefined
  const colorOf = colorMapOf(statuses)
  const mgr = useStatusManager({ projectId, entityType: 'risk', kind: 'riskstatus', statuses, reload: reloadStatuses })
  const onUpdated = (u: Risk) => setRisks(prev => prev.map(r => (r.id === u.id ? u : r)))
  const update = (id: string, patch: Parameters<typeof api.risks.update>[1]) => void api.risks.update(id, patch).then(onUpdated)
  const remove = (id: string) => void api.risks.remove(id).then(() => setRisks(prev => prev.filter(r => r.id !== id)))
  const { itemProps, reorder, moveBy } = useListReorder(risks, next => setRisks(next), ids => api.risks.reorder(projectId, ids))

  if (risks.length === 0 && blockers.length === 0)
    return <><div className="pp-toolbar">{mgr.button}</div><p style={EMPTY}>No risks or blockers.</p>{mgr.modal}</>

  return (
    <>
      <div className="pp-toolbar">{risks.length > 0 && <ViewToggle view={view} setView={setView} />}{mgr.button}</div>
      {risks.length > 0 && (view === 'board' ? (
        <EntityBoard
          labelOf={r => r.title} items={risks} columns={statusCols(statusKeys, statusDots(RISK_STATUS_DOT, statuses))} statusOf={r => r.status}
          onRestatus={(r, status) => update(r.id, { status })}
          onReorder={reorder}
          onAddColumn={onAddNew}
          renderCard={r => (
            <div className="ab-task-foot" style={{ justifyContent: 'space-between' }}>
              <span className="ab-task-title">{r.title}</span>
              <StatusBadge kind="severity" value={r.severity} />
              <RowActions title={r.title} onDelete={() => remove(r.id)} />
            </div>
          )}
        />
      ) : (
        <ul className="pp-rows">
          {risks.map(r => (
            <RiskListRow key={r.id} risk={r} phases={phases} update={update} remove={remove} dragProps={itemProps(r.id)} move={delta => void moveBy(r.id, delta)}
              statusKeys={statusKeys} onAddNew={onAddNew} colorOf={colorOf} />
          ))}
        </ul>
      ))}
      {mgr.modal}
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

function RiskListRow({ risk, phases = [], update, remove, dragProps, move, statusKeys = RISK_STATUSES, onAddNew, colorOf }: {
  risk: Risk
  phases?: Phase[]
  update: (id: string, patch: Parameters<typeof api.risks.update>[1]) => void
  remove: (id: string) => void
  dragProps: React.HTMLAttributes<HTMLLIElement> & { draggable?: boolean }
  /** Touch/keyboard reorder — dragging is mouse-only. */
  move?: (delta: -1 | 1) => void
  statusKeys?: string[]
  onAddNew?: () => void
  colorOf?: (key: string) => string | undefined
}) {
  const [open, setOpen] = useState(false)
  const editable = useEditable(risk.title, t => update(risk.id, { title: t }))
  return (
    <li className="pp-row pp-row-expandable pp-row-managed" {...dragProps}>
      <div className="pp-row-main-wrap">
        <button type="button" className="pp-row-main" onClick={() => setOpen(v => !v)} aria-expanded={open}>
          <span className="pp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {editable.node ?? <span className="pp-row-title">{risk.title}</span>}
        </button>
        <PhaseChip phaseId={risk.phase_id} phases={phases} />
        <InlineStatusSelect kind="severity" value={risk.severity} options={RISK_SEVERITIES}
          onChange={s => update(risk.id, { severity: s })} label={`Change severity of ${risk.title}`} />
        <InlineStatusSelect kind="riskstatus" value={risk.status} options={statusKeys}
          onChange={s => update(risk.id, { status: s })} label={`Change status of ${risk.title}`} onAddNew={onAddNew} colorOf={colorOf} />
        <RowActions title={risk.title} onEdit={editable.start} onDelete={() => remove(risk.id)} dragHandle
          onMoveUp={move && (() => move(-1))} onMoveDown={move && (() => move(1))} />
      </div>
      {open && (
        <div className="pp-task-details">
          {risk.description && <p className="pp-row-desc">{risk.description}</p>}
          {risk.mitigation && <p className="pp-row-desc"><strong>Mitigation:</strong> {risk.mitigation}</p>}
          <PhasePicker phaseId={risk.phase_id} phases={phases} label={`Phase for ${risk.title}`}
            onChange={phase_id => update(risk.id, { phase_id })} />
          <Attachments entityType="risk" entityId={risk.id} projectId={risk.project_id} label={risk.title} />
        </div>
      )}
    </li>
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

function CommentsSection({ comments, setComments }: {
  comments: Comment[]; setComments: React.Dispatch<React.SetStateAction<Comment[]>>
}) {
  const [view, setView] = useState<'list' | 'card'>('list')
  const onUpdated = (u: Comment) => setComments(prev => prev.map(c => (c.id === u.id ? u : c)))
  const update = (id: string, patch: Parameters<typeof api.comments.update>[1]) => void api.comments.update(id, patch).then(onUpdated)
  const remove = (id: string) => void api.comments.remove(id).then(() => setComments(prev => prev.filter(c => c.id !== id)))

  if (comments.length === 0) return <p style={EMPTY}>No comments yet.</p>

  return (
    <>
      <div className="pp-toolbar">
        <div className="ab-seg" role="group" aria-label="Comments view">
          <button type="button" aria-pressed={view === 'list'} className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button>
          <button type="button" aria-pressed={view === 'card'} className={view === 'card' ? 'active' : ''} onClick={() => setView('card')}>Cards</button>
        </div>
      </div>
      <div className={view === 'card' ? 'pp-comment-cards' : 'pp-rows'}>
        {comments.map(c => (
          <CommentItem key={c.id} comment={c} card={view === 'card'} update={update} remove={remove} />
        ))}
      </div>
    </>
  )
}

function CommentItem({ comment, card, update, remove }: {
  comment: Comment; card: boolean
  update: (id: string, patch: Parameters<typeof api.comments.update>[1]) => void
  remove: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(comment.body)
  const save = () => { setEditing(false); if (draft.trim() && draft !== comment.body) update(comment.id, { body: draft }) }
  return (
    <div className={card ? 'pp-comment-card' : 'pp-row pp-row-stacked'}>
      <div className="pp-comment-head">
        <InlineStatusSelect kind="commentstatus" value={comment.status} options={COMMENT_STATUSES}
          onChange={s => update(comment.id, { status: s })} label="Change comment status" />
        <span className="pp-comment-head-spacer" />
        <RowActions title="comment" onEdit={() => { setDraft(comment.body); setEditing(true) }} onDelete={() => remove(comment.id)} />
      </div>
      {editing ? (
        <div className="pp-comment-edit">
          <textarea className="input" autoFocus value={draft} aria-label="Edit comment"
            onChange={e => setDraft(e.target.value)} />
          <div className="pp-comment-edit-actions">
            <button type="button" className="btn btn-solid btn-sm" onClick={save}>Save</button>
            <button type="button" className="btn btn-outline btn-sm" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="pp-comment-body ab-prose"><Markdown markdown={comment.body} /></div>
      )}
      <span className="pp-meta">{comment.author_display ?? comment.entity_type} · {(comment.updated_at ?? comment.created_at).slice(0, 10)}</span>
    </div>
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
