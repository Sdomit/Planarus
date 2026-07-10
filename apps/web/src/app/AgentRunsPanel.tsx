import { useCallback, useEffect, useState } from 'react'
import { api, type AgentRun, type AgentRunAnalytics } from '../api/client'
import { fmtTimestamp } from './format'
import { StatusBadge } from './StatusBadge'

const FAMILIES = ['claude', 'chatgpt', 'codex', 'opencode', 'cursor', 'custom', 'unspecified']
const MODES = ['', 'plan', 'implement', 'review', 'debug', 'summarize']

// Reuses the shared .ab-kpi tile classes (same visual as Cockpit/Dashboard).
function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="ab-kpi">
      <div className="ab-kpi-label">{label}</div>
      <div className="ab-kpi-val">{value}</div>
    </div>
  )
}

function fmtDuration(minutes: number | null): string {
  if (minutes === null) return '—'
  return minutes >= 90 ? `${(minutes / 60).toFixed(1)} h` : `${Math.round(minutes)} min`
}

export default function AgentRunsPanel({ projectId }: { projectId: string }) {
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [analytics, setAnalytics] = useState<AgentRunAnalytics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [family, setFamily] = useState('claude')
  const [mode, setMode] = useState('')
  const [agentName, setAgentName] = useState('')
  const [summary, setSummary] = useState('')
  const [saving, setSaving] = useState(false)

  const reload = useCallback(() => {
    Promise.all([api.agentRuns.list(projectId), api.agentRuns.analytics(projectId)])
      .then(([r, a]) => {
        setRuns(r)
        setAnalytics(a)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [projectId])

  useEffect(reload, [reload])

  const logRun = (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    api.agentRuns
      .create(projectId, {
        agent_family: family,
        mode: mode || null,
        agent_name: agentName.trim() || null,
        summary: summary.trim() || null,
      })
      .then(() => {
        setSummary('')
        setAgentName('')
        reload()
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false))
  }

  const finish = (run: AgentRun, status: 'succeeded' | 'failed' | 'canceled') => {
    api.agentRuns
      .update(run.id, { status })
      .then(reload)
      .catch((e: Error) => setError(e.message))
  }

  if (error) return <p className="dp-state dp-error">{error}</p>
  if (!analytics) return <p className="dp-state">Loading agent runs…</p>

  const topFamily =
    Object.entries(analytics.by_family).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—'

  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <div className="ab-kpis" style={{ marginBottom: 0 }}>
        <Tile label="Total runs" value={String(analytics.total)} />
        <Tile
          label="Success rate"
          value={analytics.success_rate === null ? '—' : `${Math.round(analytics.success_rate * 100)}%`}
        />
        <Tile label="Avg duration" value={fmtDuration(analytics.avg_duration_minutes)} />
        <Tile label="Most used" value={topFamily} />
      </div>

      <form className="card" style={{ padding: 'var(--space-5)' }} onSubmit={logRun}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Log an agent run</div>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-field">
            <label className="form-label" htmlFor="ar-family">Agent</label>
            <select id="ar-family" className="input select" value={family} onChange={(e) => setFamily(e.target.value)}>
              {FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="ar-mode">Mode</label>
            <select id="ar-mode" className="input select" value={mode} onChange={(e) => setMode(e.target.value)}>
              {MODES.map((m) => <option key={m} value={m}>{m || '(none)'}</option>)}
            </select>
          </div>
          <div className="form-field" style={{ flex: 1, minWidth: 160 }}>
            <label className="form-label" htmlFor="ar-name">Model / agent name</label>
            <input id="ar-name" className="input" value={agentName} placeholder="e.g. claude-fable-5"
              onChange={(e) => setAgentName(e.target.value)} maxLength={120} />
          </div>
          <div className="form-field" style={{ flex: 2, minWidth: 200 }}>
            <label className="form-label" htmlFor="ar-summary">Summary</label>
            <input id="ar-summary" className="input" value={summary} placeholder="What is this run doing?"
              onChange={(e) => setSummary(e.target.value)} maxLength={4000} />
          </div>
          <button type="submit" className="btn btn-solid btn-sm" disabled={saving}>
            {saving ? 'Logging…' : 'Log run'}
          </button>
        </div>
      </form>

      {runs.length === 0 ? (
        <div className="ab-empty">
          <h3>No runs logged yet</h3>
          <p>Record each agent session here to build execution telemetry.</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
          {runs.map((run) => (
            <div
              key={run.id}
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'center',
                padding: '8px 4px',
                borderBottom: '1px solid var(--border-subtle, rgba(128,128,128,.15))',
              }}
            >
              <span className="badge badge-neutral badge-sm">{run.agent_family}</span>
              {run.mode && <span className="badge badge-neutral badge-sm">{run.mode}</span>}
              <span style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-sm)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {run.summary || run.agent_name || run.id}
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }} title={run.started_at}>
                {fmtTimestamp(run.started_at)}
              </span>
              <StatusBadge kind="agentrun" value={run.status} />
              {run.status === 'started' && (
                <>
                  <button type="button" className="btn btn-outline btn-xs" onClick={() => finish(run, 'succeeded')}>✓ done</button>
                  <button type="button" className="btn btn-ghost btn-xs" onClick={() => finish(run, 'failed')}>✕ failed</button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
