import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import NotificationsBell from './NotificationsBell'

vi.mock('../api/client', () => ({
  api: {
    notifications: {
      feed: vi.fn(async () => ({
        generated_at: 't',
        items: [
          {
            id: 'approval_pending:apr_1',
            kind: 'approval_pending',
            severity: 'action',
            title: 'Proposal awaiting review: task.create',
            detail: 'origin mcp',
            project_id: 'proj_1',
            project_title: 'Demo',
            at: '2026-07-10T12:00:00+00:00',
          },
          {
            id: 'task_overdue:tsk_1',
            kind: 'task_overdue',
            severity: 'warn',
            title: 'Task overdue: Ship it',
            detail: 'due 2026-07-01',
            project_id: 'proj_1',
            project_title: 'Demo',
            at: '2026-07-01T00:00:00+00:00',
          },
        ],
      })),
    },
  },
}))

describe('NotificationsBell', () => {
  // No global auto-cleanup in this project's vitest setup, so unmount by hand —
  // otherwise a second render leaves two bells in the DOM.
  beforeEach(() => {
    cleanup()
    localStorage.clear()
  })

  it('clears the unread badge once the feed has been opened', async () => {
    render(<NotificationsBell projectId="proj_1" onOpenItem={vi.fn()} />)
    const btn = await screen.findByLabelText('Notifications (2)')
    fireEvent.click(btn)
    // Same two items are still in the list — they are live state, not dismissed.
    expect(screen.getByText('Task overdue: Ship it')).toBeTruthy()
    // ...but they no longer count as unread.
    expect(screen.getByLabelText('Notifications (0)')).toBeTruthy()
  })

  it('shows a badge count and opens the feed', async () => {
    const onOpenItem = vi.fn()
    render(<NotificationsBell projectId="proj_1" onOpenItem={onOpenItem} />)
    const btn = await screen.findByLabelText('Notifications (2)')
    fireEvent.click(btn)
    expect(screen.getByText('Proposal awaiting review: task.create')).toBeTruthy()
    expect(screen.getByText('Task overdue: Ship it')).toBeTruthy()
    expect(screen.getByText('Desktop alerts')).toBeTruthy()
    fireEvent.click(screen.getByText('Task overdue: Ship it'))
    expect(onOpenItem).toHaveBeenCalledWith(expect.objectContaining({ id: 'task_overdue:tsk_1' }))
  })
})
