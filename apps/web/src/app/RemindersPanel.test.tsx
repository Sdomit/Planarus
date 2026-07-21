import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import RemindersPanel from './RemindersPanel'

afterEach(cleanup)

const rule = {
  id: 'nrl_1',
  project_id: 'proj_1',
  channel: 'email',
  trigger_type: 'due_soon',
  enabled: true,
  to_email: 'me@example.com',
  threshold_hours: 48,
  created_at: 't',
  updated_at: 't',
}

const send = vi.fn(async () => ({
  project_id: 'proj_1',
  sent: 1,
  skipped: 0,
  failed: 0,
  outcomes: [{ rule_id: 'nrl_1', status: 'sent', reason: null, email_log_id: 'eml_1' }],
}))

vi.mock('../api/client', () => ({
  api: {
    notificationRules: {
      list: vi.fn(async () => [rule]),
      create: vi.fn(async () => rule),
      update: vi.fn(async () => ({ ...rule, enabled: false })),
    },
    reminders: {
      send: (...args: unknown[]) => send(...(args as [])),
      emailLog: vi.fn(async () => [
        {
          id: 'eml_1', project_id: 'proj_1', rule_id: 'nrl_1',
          to_email: 'me@example.com', subject: '[Planarus] P — task reminders',
          status: 'sent', error: null,
          sent_at: '2026-07-10T12:00:00+00:00', created_at: 't',
        },
      ]),
    },
  },
}))

describe('RemindersPanel', () => {
  it('lists rules and the send history', async () => {
    render(<RemindersPanel projectId="proj_1" />)
    expect(await screen.findByText('me@example.com')).toBeTruthy()
    expect(screen.getByText(/task reminders/)).toBeTruthy()
    expect(screen.getByText('sent')).toBeTruthy()
  })

  it('sends reminders now and reports the outcome', async () => {
    render(<RemindersPanel projectId="proj_1" />)
    await screen.findByText('me@example.com') // rules loaded → button enabled
    fireEvent.click(screen.getByRole('button', { name: 'Send now' }))
    await waitFor(() => expect(send).toHaveBeenCalledWith('proj_1'))
    expect(await screen.findByText(/Sent 1 · skipped 0 · failed 0/)).toBeTruthy()
  })
})
