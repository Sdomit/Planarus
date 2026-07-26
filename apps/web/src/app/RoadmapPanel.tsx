import { useEffect, useState } from 'react'
import { api, type ProjectRoadmap, type RoadmapPhase as RoadmapPhaseT, type RoadmapTaskRollup } from '../api/client'
import { EmptyState } from './EmptyState'
import { StatusBadge, toneFor } from './StatusBadge'
import { Menu, MenuItem, MenuLabel } from './Menu'
import './roadmap-panel.css'

const PHASE_STATUSES = ['planned', 'active', 'blocked', 'done', 'canceled']

const pctOf = (r: RoadmapTaskRollup) => (r.total ? Math.round((100 * r.done) / r.total) : 0)

// Reuses the shared .ab-meter progress bar (same visual as Dashboard).
function Bar({ pct, label }: { pct: number; label: string }) {
  return (
    <div
      className="ab-meter rm-bar"
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${pct}%` }} />
    </div>
  )
}

function Counts({ r }: { r: RoadmapTaskRollup }) {
  return (
    <span className="rm-counts">
      {r.done}/{r.total} done
      {r.in_progress > 0 && ` · ${r.in_progress} active`}
      {r.blocked > 0 && ` · ${r.blocked} blocked`}
    </span>
  )
}

// Compact SVG donut for the headline figure.
function Ring({ pct }: { pct: number }) {
  const r = 20
  const c = 2 * Math.PI * r
  return (
    <svg className="rm-ring" viewBox="0 0 48 48" role="img" aria-label={`${pct}% of tasks done`}>
      <circle className="rm-ring-track" cx="24" cy="24" r={r} />
      <circle className="rm-ring-fill" cx="24" cy="24" r={r} strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} />
      <text className="rm-ring-label" x="24" y="24">{pct}%</text>
    </svg>
  )
}

function Stat({ tone, n, label }: { tone: string; n: number; label: string }) {
  return (
    <div className="rm-stat" data-tone={tone}>
      <span className="rm-stat-dot" />
      <span className="rm-stat-num">{n}</span>
      <span className="rm-stat-label">{label}</span>
    </div>
  )
}

/** A roadmap phase card with a ⋮ actions menu (open-in-planning / status /
 *  rename / delete). Bar + counts + the stage list (children) render inside. */
function PhaseCard({ phase, reload, onOpenPlanning, children }: {
  phase: RoadmapPhaseT
  reload: () => void
  onOpenPlanning?: () => void
  children?: React.ReactNode
}) {
  const [renaming, setRenaming] = useState(false)
  const [draft, setDraft] = useState(phase.title)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // Every one of these used to be `void api.X().then(reload)` with no .catch, so
  // a 409 or a restarted API changed nothing and said nothing — the user clicks
  // again and concludes the app is broken (#97).
  const fail = (e: Error) => setErr(e.message)

  const setStatus = (status: string) =>
    void api.phases.update(phase.id, { status }).then(reload).catch(fail)
  const del = () => {
    setConfirmingDelete(false)
    setErr(null)
    void api.phases.remove(phase.id).then(reload).catch(fail)
  }
  const rename = () => {
    setRenaming(false)
    const t = draft.trim()
    if (t && t !== phase.title) {
      void api.phases.update(phase.id, { title: t }).then(reload).catch(fail)
    }
  }

  return (
    <div className="card rm-phase" data-tone={toneFor('phase', phase.status)}>
      <div className="rm-phase-head">
        <div className="rm-phase-title-wrap">
          <span className="rm-dot" />
          {renaming ? (
            <input className="input input-sm" autoFocus value={draft}
              onChange={e => setDraft(e.target.value)} onBlur={rename}
              onKeyDown={e => { if (e.key === 'Enter') rename(); else if (e.key === 'Escape') setRenaming(false) }} />
          ) : (
            <strong className="rm-phase-title">{phase.title}</strong>
          )}
          <StatusBadge kind="phase" value={phase.status} />
        </div>
        <span className="rm-pct">{phase.pct_done}%</span>
        <Menu label={`Actions for ${phase.title}`}>
          {onOpenPlanning && <MenuItem onClick={onOpenPlanning}>Open in Planning</MenuItem>}
          <MenuItem onClick={() => { setDraft(phase.title); setRenaming(true) }}>Rename</MenuItem>
          <MenuLabel>Set status</MenuLabel>
          {PHASE_STATUSES.map(s => <MenuItem key={s} onClick={() => setStatus(s)}>{s}</MenuItem>)}
          {/* Two steps, like every other delete in the app: RowActions' inline
              confirm, CanvasPanel's window.confirm, Dashboard's type-to-confirm.
              This one deleted on a single menu click (#97). The ellipsis says
              another step is coming. */}
          <MenuItem danger onClick={() => { setErr(null); setConfirmingDelete(true) }}>
            Delete phase…
          </MenuItem>
        </Menu>
      </div>
      {confirmingDelete && (
        <div className="rm-confirm" role="alertdialog" aria-label={`Delete ${phase.title}?`}>
          <p className="rm-confirm-text">
            Delete <strong>{phase.title}</strong>? Its {phase.stages.length === 1
              ? '1 stage is'
              : `${phase.stages.length} stages are`} deleted
            {phase.tasks.total > 0 && (
              <> and {phase.tasks.total === 1 ? '1 task' : `${phase.tasks.total} tasks`} become
                unphased</>
            )}. Nothing else is lost — tasks, milestones, decisions and risks are kept.
          </p>
          <div className="rm-confirm-actions">
            <button type="button" className="btn btn-sm rm-confirm-del" onClick={del}>
              Delete phase
            </button>
            <button type="button" className="btn btn-outline btn-sm"
              onClick={() => setConfirmingDelete(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {err && <p className="rm-error" role="alert">{err}</p>}
      <Bar pct={phase.pct_done} label={`${phase.title} progress`} />
      <Counts r={phase.tasks} />
      {children}
    </div>
  )
}

export default function RoadmapPanel({
  projectId,
  onOpenPlanning,
}: {
  projectId: string
  onOpenPlanning?: () => void
}) {
  const [roadmap, setRoadmap] = useState<ProjectRoadmap | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = () => {
    api.roadmap.get(projectId).then(setRoadmap).catch((e: Error) => setError(e.message))
  }

  useEffect(() => {
    setRoadmap(null)
    setError(null)
    api.roadmap
      .get(projectId)
      .then(setRoadmap)
      .catch((e: Error) => setError(e.message))
  }, [projectId])

  if (error) return <p className="dp-state dp-error">{error}</p>
  if (!roadmap) return <p className="dp-state">Loading roadmap…</p>

  const t = roadmap.totals

  return (
    <div className="rm">
      <div className="card rm-summary">
        <Ring pct={roadmap.pct_done} />
        <div className="rm-summary-main">
          <h3 className="rm-summary-title">Overall progress</h3>
          <div className="rm-stats">
            <Stat tone="neutral" n={t.total} label="tasks" />
            <Stat tone="success" n={t.done} label="done" />
            <Stat tone="accent" n={t.in_progress} label="active" />
            <Stat tone="danger" n={t.blocked} label="blocked" />
          </div>
        </div>
      </div>

      {roadmap.phases.length === 0 && (
        <EmptyState
          icon={
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 22V4M4 4h11l-2 3 2 3H4" />
            </svg>
          }
          title="No phases yet"
          hint="Create phases and tasks in Planning to see the roadmap take shape."
          action={onOpenPlanning ? { label: 'Open Planning', onClick: onOpenPlanning } : undefined}
        />
      )}

      {roadmap.phases.map((phase) => (
        <PhaseCard key={phase.id} phase={phase} reload={reload} onOpenPlanning={onOpenPlanning}>
          {phase.stages.length > 0 && (
            <div className="rm-stages">
              {phase.stages.map((stage) => (
                <div key={stage.id} className="rm-stage" data-tone={toneFor('phase', stage.status)}>
                  <div className="rm-stage-rail">
                    <span className="rm-stage-node" />
                  </div>
                  <div className="rm-stage-main">
                    <div className="rm-stage-head">
                      <span className="rm-stage-title">{stage.title}</span>
                      <StatusBadge kind="phase" value={stage.status} />
                      <span className="rm-pct rm-pct-sm">{stage.pct_done}%</span>
                    </div>
                    <Bar pct={stage.pct_done} label={`${stage.title} progress`} />
                    <Counts r={stage.tasks} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </PhaseCard>
      ))}

      {roadmap.unphased.total > 0 && (
        <div className="card rm-phase rm-unphased" data-tone="neutral">
          <div className="rm-phase-head">
            <div className="rm-phase-title-wrap">
              <span className="rm-dot" />
              <strong className="rm-phase-title">Unphased tasks</strong>
            </div>
            <span className="rm-pct">{pctOf(roadmap.unphased)}%</span>
          </div>
          <Bar pct={pctOf(roadmap.unphased)} label="Unphased task progress" />
          <div className="rm-unphased-foot">
            <Counts r={roadmap.unphased} />
            {onOpenPlanning && (
              <button type="button" className="btn btn-outline btn-sm" onClick={onOpenPlanning}>
                Assign tasks
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
