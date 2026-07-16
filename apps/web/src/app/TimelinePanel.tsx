import { useEffect, useState } from 'react'
import { api, type ProjectTimeline, type TimelineEvent } from '../api/client'
import './timeline-panel.css'

// event_type → StatusBadge-style tone, used only for the node colour.
function eventTone(t: string): string {
  if (t === 'create') return 'success'
  if (t === 'update') return 'info'
  if (t.startsWith('delete') || t === 'purge') return 'danger'
  if (t.includes('email') || t === 'approve') return 'warning'
  return 'neutral'
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())

function dayLabel(iso: string, now = new Date()): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const diff = Math.round((startOfDay(now).getTime() - startOfDay(d).getTime()) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

function timeLabel(iso: string): string {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

// Groups events into consecutive same-day buckets. Input is already newest-first,
// so consecutive grouping == correct grouping and order is preserved.
export function groupEventsByDay(events: TimelineEvent[]): { key: string; events: TimelineEvent[] }[] {
  const out: { key: string; events: TimelineEvent[] }[] = []
  for (const ev of events) {
    const d = new Date(ev.at)
    const key = isNaN(d.getTime()) ? ev.at : `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    const last = out[out.length - 1]
    if (last && last.key === key) last.events.push(ev)
    else out.push({ key, events: [ev] })
  }
  return out
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
        <div className="ab-empty-art" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
          </svg>
        </div>
        <h3>No activity yet</h3>
        <p>Every audited change to this project will appear here.</p>
      </div>
    )
  }

  const evs = timeline.events
  const created = evs.filter((e) => e.event_type === 'create').length
  const updated = evs.filter((e) => e.event_type === 'update').length
  const other = evs.length - created - updated
  const groups = groupEventsByDay(evs)

  return (
    <div className="tl">
      <div className="card tl-summary">
        <span className="tl-count">{evs.length}</span>
        <span className="tl-sub">audited events · newest first</span>
        <span className="tl-stats">
          {created > 0 && (
            <span className="tl-stat" data-tone="success"><span className="tl-stat-dot" />{created} created</span>
          )}
          {updated > 0 && (
            <span className="tl-stat" data-tone="info"><span className="tl-stat-dot" />{updated} updated</span>
          )}
          {other > 0 && (
            <span className="tl-stat" data-tone="neutral"><span className="tl-stat-dot" />{other} other</span>
          )}
        </span>
      </div>

      {groups.map((group) => (
        <div key={group.key} className="card tl-group">
          <div className="tl-day">{dayLabel(group.events[0].at)}</div>
          <ol className="tl-list">
            {group.events.map((ev) => (
              <li key={ev.id} className="tl-item" data-tone={eventTone(ev.event_type)}>
                <div className="tl-rail">
                  <span className="tl-node" />
                </div>
                <div className="tl-body">
                  <div className="tl-line">
                    <span className="tl-label">{ev.label}</span>
                    <time className="tl-time" dateTime={ev.at} title={ev.at}>{timeLabel(ev.at)}</time>
                  </div>
                  <div className="tl-meta">
                    <span className="tl-chip">{ev.entity_type.replace(/_/g, ' ')}</span>
                    <span className="tl-actor">{ev.actor_type}</span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}
