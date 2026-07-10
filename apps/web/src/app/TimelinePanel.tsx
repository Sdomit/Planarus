import { useEffect, useState } from 'react'
import { api, type ProjectTimeline } from '../api/client'
import { fmtTimestamp } from './format'

const DOT: Record<string, string> = {
  create: 'var(--success, #2e9e5b)',
  update: 'var(--info, #4c7dff)',
  email_send: 'var(--warning, #d99a2b)',
}

export default function TimelinePanel({ projectId }: { projectId: string }) {
  const [timeline, setTimeline] = useState<ProjectTimeline | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setTimeline(null)
    setError(null)
    api.timeline
      .get(projectId)
      .then(setTimeline)
      .catch((e: Error) => setError(e.message))
  }, [projectId])

  if (error) return <p className="dp-state dp-error">{error}</p>
  if (!timeline) return <p className="dp-state">Loading timeline…</p>
  if (timeline.events.length === 0) {
    return (
      <div className="ab-empty">
        <h3>No activity yet</h3>
        <p>Every audited change to this project will appear here.</p>
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: 'var(--space-5)' }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 8 }}>
        Latest {timeline.events.length} audited events, newest first
      </div>
      <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {timeline.events.map((ev) => (
          <li
            key={ev.id}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'baseline',
              padding: '6px 0',
              borderBottom: '1px solid var(--border-subtle, rgba(128,128,128,.15))',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                flexShrink: 0,
                alignSelf: 'center',
                background: DOT[ev.event_type] ?? 'var(--text-tertiary, #888)',
              }}
            />
            <span style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-sm)' }}>{ev.label}</span>
            <span className="badge badge-neutral badge-sm">{ev.actor_type}</span>
            <span
              style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}
              title={ev.at}
            >
              {fmtTimestamp(ev.at)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
