import { describe, expect, it } from 'vitest'
import { buildAttention, DUE_SOON_DAYS, STALE_DAYS, type AttentionInput } from './attention'

const NOW = new Date('2026-07-26T12:00:00Z')
const day = (n: number) => new Date(NOW.getTime() + n * 86_400_000).toISOString()

const task = (over: Partial<AttentionInput['tasks'][number]> = {}) => ({
  id: 't1', project_id: 'p1', phase_id: null, stage_id: null, parent_task_id: null,
  title: 'A task', description: null, status: 'todo', priority: null, due_at: null,
  sort_order: 0, assignee_id: null, assignee_display: null,
  created_at: day(-30), updated_at: day(-1), ...over,
})

const milestone = (over: Record<string, unknown> = {}) => ({
  id: 'm1', project_id: 'p1', phase_id: null, title: 'A milestone', description: null,
  status: 'planned', target_date: null, sort_order: 0,
  created_at: day(-30), updated_at: day(-1), ...over,
}) as AttentionInput['milestones'][number]

const blocker = (over: Record<string, unknown> = {}) => ({
  id: 'b1', project_id: 'p1', task_id: null, title: 'A blocker', description: null,
  status: 'open', created_at: day(-2), updated_at: day(-2), ...over,
}) as AttentionInput['blockers'][number]

const feedItem = (over: Record<string, unknown> = {}) => ({
  id: 'n1', kind: 'approval_pending', severity: 'warning', title: 'Proposal waiting',
  detail: null, project_id: 'p2', project_title: 'Other Project', at: day(0), ...over,
}) as AttentionInput['feed'][number]

const input = (over: Partial<AttentionInput> = {}): AttentionInput => ({
  projectId: 'p1', tasks: [], milestones: [], blockers: [], pendingApprovals: 0, feed: [], ...over,
})

describe('buildAttention', () => {
  it('is empty when nothing is wrong', () => {
    expect(buildAttention(input({ tasks: [task()] }), NOW)).toEqual([])
  })

  it('surfaces work in OTHER projects, which the bell cannot', () => {
    // The bell is scoped to the selected project, so an agent proposing writes to
    // project B while you sit in project A reaches you nowhere.
    const rows = buildAttention(input({ feed: [feedItem(), feedItem({ id: 'n2', project_id: 'p1' })] }), NOW)
    expect(rows).toHaveLength(1)
    expect(rows[0].kind).toBe('other-project')
    expect(rows[0].detail).toBe('in Other Project')
    // Carries the item so the caller can switch project before navigating.
    expect(rows[0].item?.project_id).toBe('p2')
  })

  it('counts pending approvals once, not per proposal', () => {
    const rows = buildAttention(input({ pendingApprovals: 3 }), NOW)
    expect(rows.map(r => r.title)).toEqual(['3 proposals awaiting your review'])
  })

  it('singularises one proposal', () => {
    expect(buildAttention(input({ pendingApprovals: 1 }), NOW)[0].title)
      .toBe('1 proposal awaiting your review')
  })

  it('separates overdue from due-soon, and ignores what is further out', () => {
    const rows = buildAttention(input({
      tasks: [
        task({ id: 'late', due_at: day(-2) }),
        task({ id: 'today', due_at: day(0) }),
        task({ id: 'soon', due_at: day(DUE_SOON_DAYS) }),
        task({ id: 'later', due_at: day(DUE_SOON_DAYS + 1) }),
      ],
    }), NOW)
    expect(rows.map(r => [r.kind, r.detail])).toEqual([
      ['overdue-task', 'task 2 days overdue'],
      ['due-soon', 'task due today'],
      ['due-soon', `task due in ${DUE_SOON_DAYS} days`],
    ])
  })

  it('does not round a few hours late up to a whole day', () => {
    // Flooring the signed difference reported "1 day overdue" for a task three
    // hours past its time — a number the user can see is wrong.
    const threeHoursAgo = new Date(NOW.getTime() - 3 * 3_600_000).toISOString()
    const rows = buildAttention(input({ tasks: [task({ due_at: threeHoursAgo })] }), NOW)
    expect(rows.map(r => [r.kind, r.detail])).toEqual([['overdue-task', 'task overdue']])
  })

  it('does not round a few hours early down into overdue', () => {
    const inSixHours = new Date(NOW.getTime() + 6 * 3_600_000).toISOString()
    const rows = buildAttention(input({ tasks: [task({ due_at: inSixHours })] }), NOW)
    expect(rows.map(r => [r.kind, r.detail])).toEqual([['due-soon', 'task due today']])
  })

  it('says the same about a milestone hours past its target', () => {
    const rows = buildAttention(input({
      milestones: [milestone({ target_date: new Date(NOW.getTime() - 3_600_000).toISOString() })],
    }), NOW)
    expect(rows[0].detail).toBe('milestone past its target')
  })

  it('ignores due dates on finished work', () => {
    const rows = buildAttention(input({
      tasks: [task({ status: 'done', due_at: day(-5) }), task({ id: 'x', status: 'canceled', due_at: day(-5) })],
    }), NOW)
    expect(rows).toEqual([])
  })

  it('flags a stale in_progress task but not a stale todo', () => {
    const rows = buildAttention(input({
      tasks: [
        task({ id: 'stale', status: 'in_progress', updated_at: day(-STALE_DAYS) }),
        task({ id: 'fresh', status: 'in_progress', updated_at: day(-1) }),
        task({ id: 'idle-todo', status: 'todo', updated_at: day(-90) }),
      ],
    }), NOW)
    expect(rows.map(r => [r.kind, r.detail])).toEqual([
      ['stale-task', `in progress, untouched for ${STALE_DAYS} days`],
    ])
  })

  it('flags a milestone past its target, but not an achieved one', () => {
    const rows = buildAttention(input({
      milestones: [
        milestone({ id: 'missed', target_date: day(-1) }),
        milestone({ id: 'hit', status: 'achieved', target_date: day(-9) }),
        milestone({ id: 'future', target_date: day(30) }),
      ],
    }), NOW)
    expect(rows.map(r => [r.kind, r.detail])).toEqual([
      ['overdue-milestone', 'milestone 1 day past its target'],
    ])
  })

  it('counts only open blockers', () => {
    const rows = buildAttention(input({
      blockers: [blocker(), blocker({ id: 'b2', status: 'resolved' })],
    }), NOW)
    expect(rows.map(r => r.kind)).toEqual(['blocker'])
  })

  it('reads worst-first: other projects, approvals, blockers, then late work', () => {
    const rows = buildAttention(input({
      feed: [feedItem()],
      pendingApprovals: 1,
      blockers: [blocker()],
      tasks: [task({ due_at: day(-1) }), task({ id: 's', status: 'in_progress', updated_at: day(-30) })],
      milestones: [milestone({ target_date: day(-1) })],
    }), NOW)
    expect(rows.map(r => r.kind)).toEqual([
      'other-project', 'approval', 'blocker', 'overdue-task', 'overdue-milestone', 'stale-task',
    ])
    // Tone drives the dot colour: already-wrong vs will-be-wrong vs FYI.
    expect(rows.filter(r => r.tone === 'danger').map(r => r.kind))
      .toEqual(['blocker', 'overdue-task', 'overdue-milestone'])
  })
})
