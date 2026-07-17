import { useEffect, useState, type ReactNode } from 'react'
import {
  api, GitRepoLink, Project, Task, Risk, Milestone, Decision,
  type ProjectRoadmap, type TimelineEvent,
} from '../api/client'
import { StatusBadge } from './StatusBadge'
import { Icon } from './Icon'
import { dayLabel } from './date'
import './cockpit-panel.css'

const DONE_TASK = new Set(['done', 'canceled'])
const CLOSED_RISK = new Set(['mitigated', 'accepted', 'closed'])
const DONE_MILESTONE = new Set(['achieved', 'missed', 'canceled'])

interface CockpitPanelProps {
  projectId: string
  onClose: () => void
}

export default function CockpitPanel({ projectId }: CockpitPanelProps) {
  const [project, setProject] = useState<Project | null>(null)
  const [git, setGit] = useState<GitRepoLink | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [risks, setRisks] = useState<Risk[]>([])
  const [milestones, setMilestones] = useState<Milestone[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [roadmap, setRoadmap] = useState<ProjectRoadmap | null>(null)
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [phaseCount, setPhaseCount] = useState(0)
  const [pending, setPending] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { load() }, [projectId])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [proj, phases, tks, rks, mils, decs, gitLink, approvals, rm, tl] = await Promise.all([
        api.projects.get(projectId),
        api.phases.list(projectId),
        api.tasks.list(projectId),
        api.risks.list(projectId),
        api.milestones.list(projectId).catch(() => []),
        api.decisions.list(projectId).catch(() => []),
        api.git.get(projectId).catch(() => null),
        api.approvals.list(projectId, 'pending').catch(() => []),
        api.roadmap.get(projectId).catch(() => null),
        api.timeline.get(projectId, 6).catch(() => null),
      ])
      setProject(proj)
      setPhaseCount(phases.length)
      setTasks(tks)
      setRisks(rks)
      setMilestones(mils)
      setDecisions(decs)
      setGit(gitLink)
      setPending(approvals.length)
      setRoadmap(rm)
      setEvents(tl?.events ?? [])
    } catch {
      setError('Could not load the cockpit. Make sure the backend is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="ab-state"><span className="spinner spinner-sm" /> Loading cockpit…</div>
  if (error) {
    return (
      <div className="ab-state ab-state-error">
        <p style={{ margin: 0 }}>{error}</p>
        <button className="btn btn-outline btn-sm" type="button" onClick={load}>Retry</button>
      </div>
    )
  }
  if (!project) return <div className="ab-state"><p style={{ margin: 0 }}>Project not found.</p></div>

  const openTasks = tasks.filter((t) => !DONE_TASK.has(t.status)).length
  const openRisks = risks.filter((r) => !CLOSED_RISK.has(r.status)).length
  const openMilestones = milestones.filter((m) => !DONE_MILESTONE.has(m.status)).length

  const kpis = [
    { label: 'Phases', value: phaseCount, foot: 'in plan' },
    { label: 'Open tasks', value: openTasks, foot: `of ${tasks.length} total` },
    { label: 'Open risks', value: openRisks, foot: openRisks ? 'need attention' : 'clear' },
    { label: 'Milestones', value: openMilestones, foot: `of ${milestones.length} total` },
    { label: 'Decisions', value: decisions.length, foot: 'recorded' },
    { label: 'Pending approvals', value: pending, foot: pending ? 'awaiting review' : 'queue clear' },
  ]

  const upcoming = milestones
    .filter((m) => m.target_date && !DONE_MILESTONE.has(m.status))
    .sort((a, b) => (a.target_date! < b.target_date! ? -1 : 1))
    .slice(0, 4)

  return (
    <section className="anim-fade-in-up" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div className="ab-section-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', minWidth: 0 }}>
          <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: '-0.015em', margin: 0, color: 'var(--text-primary)' }}>
            {project.title}
          </h2>
          <StatusBadge kind="project" value={project.status} />
        </div>
      </div>

      {project.summary && (
        <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>{project.summary}</p>
      )}

      <div className="ab-kpis stagger">
        {kpis.map((k) => (
          <div className="ab-kpi anim-fade-in-up" key={k.label}>
            <div className="ab-kpi-label">{k.label}</div>
            <div className="ab-kpi-val">{k.value}</div>
            <div className="ab-kpi-foot">{k.foot}</div>
          </div>
        ))}
      </div>

      <div className="ck-grid">
        <PhaseProgress roadmap={roadmap} />
        <UpcomingMilestones milestones={upcoming} />
        <RecentActivity events={events} />
      </div>

      <GitSummary git={git} />
    </section>
  )
}

function WidgetCard({ icon, title, children }: { icon: string; title: string; children: ReactNode }) {
  return (
    <div className="card ck-widget">
      <div className="ck-widget-head">
        <Icon name={icon} className="ic-16" />
        <span className="ck-widget-title">{title}</span>
      </div>
      {children}
    </div>
  )
}

function PhaseProgress({ roadmap }: { roadmap: ProjectRoadmap | null }) {
  const phases = roadmap?.phases ?? []
  return (
    <WidgetCard icon="columns" title="Phase progress">
      {phases.length === 0 ? (
        <p className="ck-empty">No phases yet.</p>
      ) : (
        <ul className="ck-list">
          {phases.slice(0, 6).map((p) => (
            <li key={p.id} className="ck-progress-row">
              <span className="ck-progress-name">{p.title}</span>
              <span className="ab-meter ck-meter" role="progressbar" aria-label={`${p.title} progress`}
                aria-valuenow={p.pct_done} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${p.pct_done}%` }} />
              </span>
              <span className="ck-progress-pct">{p.pct_done}%</span>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}

function UpcomingMilestones({ milestones }: { milestones: Milestone[] }) {
  return (
    <WidgetCard icon="calendar" title="Upcoming milestones">
      {milestones.length === 0 ? (
        <p className="ck-empty">No dated milestones.</p>
      ) : (
        <ul className="ck-list">
          {milestones.map((m) => (
            <li key={m.id} className="ck-milestone-row">
              <span className="ck-milestone-title">{m.title}</span>
              <span className="ck-milestone-date">{m.target_date}</span>
              <StatusBadge kind="milestone" value={m.status} />
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}

function RecentActivity({ events }: { events: TimelineEvent[] }) {
  return (
    <WidgetCard icon="clock" title="Recent activity">
      {events.length === 0 ? (
        <p className="ck-empty">No activity yet.</p>
      ) : (
        <ul className="ck-list">
          {events.slice(0, 6).map((e) => (
            <li key={e.id} className="ck-activity-row">
              <span className="ck-activity-label">{e.label}</span>
              <span className="ck-activity-when">{dayLabel(e.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}

function GitSummary({ git }: { git: GitRepoLink | null }) {
  const label = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--space-3)' }}>
      <Icon name="code" className="ic-16" />
      <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>Git</span>
      <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>read-only</span>
    </div>
  )

  if (!git || !git.is_repo) {
    return (
      <div className="card" style={{ padding: 'var(--space-5)' }}>
        {label}
        <p style={{ margin: 0, color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
          {git?.message ?? 'No Git metadata available.'}
        </p>
      </div>
    )
  }

  const dirtyTone = git.is_dirty ? 'sbadge--warning' : 'sbadge--success'
  const dirtyText = git.is_dirty ? `${git.dirty_count} uncommitted` : 'clean'

  const rows: { k: string; v: ReactNode }[] = [
    {
      k: 'Branch',
      v: git.detached
        ? <span style={{ color: 'var(--text-secondary)' }}>detached HEAD</span>
        : <code style={{ fontSize: 'var(--text-sm)' }}>{git.current_branch ?? '—'}</code>,
    },
    {
      k: 'Working tree',
      v: <span className={`sbadge ${dirtyTone}`}><span className="sdot" />{dirtyText}</span>,
    },
    {
      k: 'Last commit',
      v: git.last_commit_sha
        ? <span><code style={{ fontSize: 'var(--text-sm)' }}>{git.last_commit_sha}</code>{' '}{git.last_commit_subject}</span>
        : <span style={{ color: 'var(--text-tertiary)' }}>no commits yet</span>,
    },
    { k: 'Remote', v: git.remote_url ? <code style={{ fontSize: 'var(--text-sm)' }}>{git.remote_url}</code> : <span style={{ color: 'var(--text-tertiary)' }}>none</span> },
  ]

  return (
    <div className="card" style={{ padding: 'var(--space-5)' }}>
      {label}
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 'var(--space-2) var(--space-4)', margin: 0 }}>
        {rows.map((r) => (
          <div key={r.k} style={{ display: 'contents' }}>
            <dt style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', alignSelf: 'center' }}>{r.k}</dt>
            <dd style={{ margin: 0, minWidth: 0, overflowWrap: 'anywhere', color: 'var(--text-primary)' }}>{r.v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
