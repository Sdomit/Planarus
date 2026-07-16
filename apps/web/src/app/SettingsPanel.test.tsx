import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import SettingsPanel from './SettingsPanel'

afterEach(cleanup)

const base = {
  email_enabled: false,
  email_from: 'approvo@localhost',
  external_api_active: true,
  external_api_permitted_by_env: false,
  external_api_hosts_configured: false,
  email_smtp_loopback: true,
}

const update = vi.fn(async (data: Record<string, unknown>) => ({ ...base, ...data }))

vi.mock('../api/client', () => ({
  api: {
    settings: {
      get: vi.fn(async () => base),
      update: (...args: unknown[]) => update(...(args as [Record<string, unknown>])),
    },
  },
}))

describe('SettingsPanel', () => {
  it('renders loaded settings and the read-only ceiling status', async () => {
    render(<SettingsPanel />)
    expect(await screen.findByDisplayValue('approvo@localhost')).toBeTruthy()
    // env ceiling is off → the inert-switch warning is shown
    expect(screen.getByText(/Inert until/)).toBeTruthy()
  })

  it('saves the switch values and confirms', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByLabelText('Send email reminders'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith({
        email_enabled: true,
        email_from: 'approvo@localhost',
        external_api_active: true,
      }),
    )
    expect(await screen.findByText('Saved ✓')).toBeTruthy()
  })
})
