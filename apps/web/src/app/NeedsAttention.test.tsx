import { describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, within } from '@testing-library/react'
import NeedsAttention from './NeedsAttention'
import type { AttentionInput } from './attention'

const NOW = new Date('2026-07-26T12:00:00Z')
const day = (n: number) => new Date(NOW.getTime() + n * 86_400_000).toISOString()

const input = (over: Partial<AttentionInput> = {}): AttentionInput => ({
  projectId: 'p1', tasks: [], milestones: [], blockers: [], pendingApprovals: 0, feed: [], ...over,
})

const feedItem = (id: string) => ({
  id, kind: 'approval_pending', severity: 'warning', title: `Item ${id}`,
  detail: null, project_id: 'p2', project_title: 'Other Project', at: day(0),
}) as AttentionInput['feed'][number]

const task = (over: Record<string, unknown> = {}) => ({
  id: 't1', project_id: 'p1', phase_id: null, stage_id: null, parent_task_id: null,
  title: 'Late task', description: null, status: 'todo', priority: null, due_at: day(-3),
  sort_order: 0, assignee_id: null, assignee_display: null,
  created_at: day(-30), updated_at: day(-1), ...over,
}) as AttentionInput['tasks'][number]

function setup(over: Partial<AttentionInput> = {}) {
  cleanup() // no RTL auto-cleanup in this project's vitest config
  const onOpenItem = vi.fn()
  const onOpenApprovals = vi.fn()
  const onOpenTasks = vi.fn()
  const { container } = render(
    <NeedsAttention
      input={input(over)}
      onOpenItem={onOpenItem}
      onOpenApprovals={onOpenApprovals}
      onOpenTasks={onOpenTasks}
      now={NOW}
    />,
  )
  return { view: within(container), onOpenItem, onOpenApprovals, onOpenTasks }
}

describe('NeedsAttention', () => {
  it('says so plainly when there is nothing to do', () => {
    const { view } = setup()
    expect(view.getByText(/Nothing needs attention/)).toBeTruthy()
    expect(view.queryByRole('button')).toBeNull()
  })

  // The whole point of the widget: CockpitPanel was an unclickable poster (#95).
  it('every row is a button', () => {
    const { view } = setup({ pendingApprovals: 2, tasks: [task()], blockers: [] })
    expect(view.getAllByRole('button')).toHaveLength(2)
  })

  it('routes an approval row to the queue', () => {
    const { view, onOpenApprovals, onOpenTasks } = setup({ pendingApprovals: 1 })
    fireEvent.click(view.getByRole('button', { name: /awaiting your review/ }))
    expect(onOpenApprovals).toHaveBeenCalledOnce()
    expect(onOpenTasks).not.toHaveBeenCalled()
  })

  it('hands a cross-project row back as its feed item, so the caller can switch project', () => {
    const { view, onOpenItem, onOpenTasks } = setup({ feed: [feedItem('n1')] })
    fireEvent.click(view.getByRole('button', { name: /Item n1/ }))
    expect(onOpenItem).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1', project_id: 'p2' }))
    expect(onOpenTasks).not.toHaveBeenCalled()
  })

  it('routes overdue work to the task list', () => {
    const { view, onOpenTasks } = setup({ tasks: [task()] })
    fireEvent.click(view.getByRole('button', { name: /Late task/ }))
    expect(onOpenTasks).toHaveBeenCalledOnce()
  })

  it('caps the list but says how many it hid', () => {
    const { view } = setup({ feed: Array.from({ length: 11 }, (_, i) => feedItem(`n${i}`)) })
    expect(view.getAllByRole('button')).toHaveLength(8)
    expect(view.getByText('+3 more')).toBeTruthy()
  })

  it('counts the rows in the header', () => {
    const { view } = setup({ pendingApprovals: 1, tasks: [task()] })
    expect(view.getByText('2')).toBeTruthy()
  })
})
