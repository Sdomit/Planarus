import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import SettingsPanel from './SettingsPanel'

afterEach(cleanup)

const base = {
  email_enabled: false,
  email_from: 'approvo@localhost',
  external_api_active: true,
  lan_mode_active: false,
  registration_open: true,
  external_api_permitted_by_env: false,
  external_api_hosts_configured: false,
  email_smtp_loopback: true,
  lan_permitted_by_env: false,
  lan_hosts_configured: false,
  auth_enabled_by_env: false,
  auth_password_enabled_by_env: false,
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
    // both env ceilings are off → each section shows its inert-switch warning
    expect(screen.getByText('AGENTBOARD_EXTERNAL_API_ENABLED=true')).toBeTruthy()
    expect(screen.getByText('AGENTBOARD_LAN_MODE_ENABLED=true')).toBeTruthy()
    expect(screen.getByLabelText('Accept teammates from the LAN')).toBeTruthy()
  })

  it('saves the LAN switch when toggled', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByLabelText('Accept teammates from the LAN'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith({ lan_mode_active: true }))
  })

  it('saves the registration switch when closed (P16.2, D30)', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByLabelText('Accept self-registration on the sign-in screen'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith({ registration_open: false }))
  })

  it('saves only the changed switch and confirms', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByLabelText('Send email reminders'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    // Only the touched key is sent — untouched switches must not get pinned
    // into DB rows (their env defaults stay live).
    await waitFor(() => expect(update).toHaveBeenCalledWith({ email_enabled: true }))
    expect(await screen.findByText('Saved ✓')).toBeTruthy()
  })
})
