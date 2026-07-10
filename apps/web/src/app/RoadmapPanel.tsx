import { useEffect, useState } from 'react'
import { api, type ProjectRoadmap, type RoadmapTaskRollup } from '../api/client'
import { StatusBadge } from './StatusBadge'

// Reuses the shared .ab-meter progress bar (same visual as Dashboard).
function Bar({ pct }: { pct: number }) {
  return (
    <div
      className="ab-meter"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      style={{ flex: 1 }}
    >
      <span style={{ width: `${pct}%` }} />
    </div>
  )
}

function Counts({ r }: { r: RoadmapTaskRollup }) {
  return (
    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
      {r.done}/{r.total} done
      {r.in_progress > 0 && ` · ${r.in_progress} active`}
      {r.blocked > 0 && ` · ${r.blocked} blocked`}
    </span>
  )
}

export default function RoadmapPanel({ projectId }: { projectId: string }) {
  const [roadmap, setRoadmap] = useState<ProjectRoadmap | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <div className="card" style={{ padding: 'var(--space-5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <strong style={{ whiteSpace: 'nowrap' }}>Overall {roadmap.pct_done}%</strong>
          <Bar pct={roadmap.pct_done} />
          <Counts r={roadmap.totals} />
        </div>
      </div>

      {roadmap.phases.length === 0 && (
        <div className="ab-empty">
          <h3>No phases yet</h3>
          <p>Create phases and tasks in Planning to see the roadmap.</p>
        </div>
      )}

      {roadmap.phases.map((phase) => (
        <div key={phase.id} className="card" style={{ padding: 'var(--space-5)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <strong style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {phase.title}
            </strong>
            <StatusBadge kind="phase" value={phase.status} />
            <Bar pct={phase.pct_done} />
            <Counts r={phase.tasks} />
          </div>
          {phase.stages.map((stage) => (
            <div
              key={stage.id}
              style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '4px 0 4px var(--space-6)' }}
            >
              <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {stage.title}
              </span>
              <StatusBadge kind="phase" value={stage.status} />
              <Bar pct={stage.pct_done} />
              <Counts r={stage.tasks} />
            </div>
          ))}
        </div>
      ))}

      {roadmap.unphased.total > 0 && (
        <div className="card" style={{ padding: 'var(--space-5)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <strong>Unphased tasks</strong>
            <Bar pct={roadmap.unphased.total ? Math.round((100 * roadmap.unphased.done) / roadmap.unphased.total) : 0} />
            <Counts r={roadmap.unphased} />
          </div>
        </div>
      )}
    </div>
  )
}
