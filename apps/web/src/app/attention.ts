import type { Blocker, Milestone, NotificationItem, Task } from '../api/client'

/**
 * "What needs attention?" — the human's answer to the question `get_active_work`
 * has answered for agents since Phase 19 (#95).
 *
 * Pure on purpose: every threshold here is a judgement call, and a judgement call
 * that lives in a component can only be tested by rendering it. `now` is injected
 * for the same reason — a date-dependent rule tested against the real clock
 * passes or fails depending on when CI runs.
 */

/** In progress and untouched for this long is stale, not active. */
export const STALE_DAYS = 10
/** Due inside this window is worth surfacing before it is late. */
export const DUE_SOON_DAYS = 3

const DONE_TASK = new Set(['done', 'canceled'])
const DONE_MILESTONE = new Set(['achieved', 'missed', 'canceled'])
const OPEN_BLOCKER = new Set(['open', 'active'])

export type AttentionKind =
  | 'other-project'
  | 'approval'
  | 'blocker'
  | 'overdue-task'
  | 'overdue-milestone'
  | 'due-soon'
  | 'stale-task'

export interface AttentionRow {
  id: string
  kind: AttentionKind
  /** 'danger' = already gone wrong; 'warn' = will if ignored; 'info' = FYI. */
  tone: 'danger' | 'warn' | 'info'
  title: string
  detail: string
  /** Present when acting on the row means leaving the current project. */
  item?: NotificationItem
}

export interface AttentionInput {
  projectId: string
  tasks: Task[]
  milestones: Milestone[]
  blockers: Blocker[]
  pendingApprovals: number
  /** Unscoped feed: the whole point is to see the projects you are NOT in. */
  feed: NotificationItem[]
}

function daysBetween(from: Date, to: Date): number {
  return Math.floor((to.getTime() - from.getTime()) / 86_400_000)
}

/** Signed distance to a deadline, split into direction and whole days.
 *
 * Flooring a signed difference reports anything under a day late as "1 day
 * overdue" — a task three hours past its time claimed a full day. Direction and
 * magnitude are computed separately so sub-day lateness says so instead. */
function until(target: string, now: Date): { overdue: boolean; days: number } {
  const ms = new Date(target).getTime() - now.getTime()
  return { overdue: ms < 0, days: Math.floor(Math.abs(ms) / 86_400_000) }
}

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? '' : 's'}`

/** Rows in the order a human should read them: broken, then blocked, then late. */
export function buildAttention(input: AttentionInput, now = new Date()): AttentionRow[] {
  const rows: AttentionRow[] = []

  // Work happening somewhere else. The bell is scoped to the selected project, so
  // an agent proposing writes to project B while you sit in project A reaches you
  // nowhere at all — the gap this list exists to close.
  for (const item of input.feed) {
    if (item.project_id === input.projectId) continue
    rows.push({
      id: `other:${item.id}`,
      kind: 'other-project',
      tone: item.severity === 'critical' || item.severity === 'danger' ? 'danger' : 'warn',
      title: item.title,
      detail: `in ${item.project_title}`,
      item,
    })
  }

  if (input.pendingApprovals > 0) {
    rows.push({
      id: 'approvals',
      kind: 'approval',
      tone: 'warn',
      title: `${input.pendingApprovals} ${input.pendingApprovals === 1 ? 'proposal' : 'proposals'} awaiting your review`,
      detail: 'nothing is applied until you approve it',
    })
  }

  for (const b of input.blockers) {
    if (!OPEN_BLOCKER.has(b.status)) continue
    rows.push({
      id: `blocker:${b.id}`,
      kind: 'blocker',
      tone: 'danger',
      title: b.title,
      detail: 'open blocker',
    })
  }

  const open = input.tasks.filter((t) => !DONE_TASK.has(t.status))
  for (const t of open) {
    if (!t.due_at) continue
    const { overdue, days } = until(t.due_at, now)
    if (overdue) {
      rows.push({
        id: `overdue:${t.id}`,
        kind: 'overdue-task',
        tone: 'danger',
        title: t.title,
        detail: days === 0 ? 'task overdue' : `task ${plural(days, 'day')} overdue`,
      })
    } else if (days <= DUE_SOON_DAYS) {
      rows.push({
        id: `soon:${t.id}`,
        kind: 'due-soon',
        tone: 'warn',
        title: t.title,
        detail: days === 0 ? 'task due today' : `task due in ${plural(days, 'day')}`,
      })
    }
  }

  for (const m of input.milestones) {
    if (DONE_MILESTONE.has(m.status) || !m.target_date) continue
    const { overdue, days } = until(m.target_date, now)
    if (overdue) {
      rows.push({
        id: `ms:${m.id}`,
        kind: 'overdue-milestone',
        tone: 'danger',
        title: m.title,
        detail: days === 0
          ? 'milestone past its target'
          : `milestone ${plural(days, 'day')} past its target`,
      })
    }
  }

  // Stale beats silent: an in_progress task nobody has touched in ten days is
  // either forgotten or finished, and both are worth a nudge.
  for (const t of open) {
    if (t.status !== 'in_progress') continue
    const idle = daysBetween(new Date(t.updated_at), now)
    if (idle >= STALE_DAYS) {
      rows.push({
        id: `stale:${t.id}`,
        kind: 'stale-task',
        tone: 'info',
        title: t.title,
        detail: `in progress, untouched for ${idle} days`,
      })
    }
  }

  return rows
}
