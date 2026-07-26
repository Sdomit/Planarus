import type { NotificationItem } from '../api/client'
import { Icon } from './Icon'
import { buildAttention, type AttentionInput, type AttentionRow } from './attention'

/**
 * The Cockpit's one clickable widget (#95).
 *
 * `CockpitPanel` was an unclickable poster: KPIs, phase rows, milestones and
 * activity, none of which went anywhere. Every row here navigates, including to
 * other projects — the feed rows carry their NotificationItem so Layout's
 * existing `openNotification` can switch project first.
 */
export default function NeedsAttention({
  input,
  onOpenItem,
  onOpenApprovals,
  onOpenTasks,
  now,
}: {
  input: AttentionInput
  onOpenItem: (item: NotificationItem) => void
  onOpenApprovals: () => void
  onOpenTasks: () => void
  now?: Date
}) {
  const rows = buildAttention(input, now)

  const activate = (row: AttentionRow) => {
    if (row.item) onOpenItem(row.item)
    else if (row.kind === 'approval') onOpenApprovals()
    else onOpenTasks()
  }

  return (
    <div className="card ck-widget ck-attention">
      <div className="ck-widget-head">
        <Icon name="bell" />
        <span className="ck-widget-title">Needs attention</span>
        {rows.length > 0 && <span className="ck-att-count">{rows.length}</span>}
      </div>
      {rows.length === 0 ? (
        <p className="ck-empty">Nothing needs attention — no overdue work, blockers or pending proposals.</p>
      ) : (
        <ul className="ck-list">
          {rows.slice(0, 8).map((row) => (
            <li key={row.id}>
              <button type="button" className="ck-att-row" onClick={() => activate(row)}>
                <span className={`ck-att-dot ck-att-${row.tone}`} aria-hidden="true" />
                <span className="ck-att-title">{row.title}</span>
                <span className="ck-att-detail">{row.detail}</span>
              </button>
            </li>
          ))}
          {rows.length > 8 && (
            // Say what is hidden rather than truncating silently.
            <li className="ck-empty">+{rows.length - 8} more</li>
          )}
        </ul>
      )}
    </div>
  )
}
