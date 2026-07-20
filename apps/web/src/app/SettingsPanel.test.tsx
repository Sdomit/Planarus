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
  // P18.2/18.4 (D42/D44) — backup switches + capability status
  backup_enabled: false,
  backup_retention: 7,
  backup_offsite: false,
  backup_supported: true,
  backup_dir_configured: true,
  backup_offsite_supported: false,
}

const update = vi.fn(async (data: Record<string, unknown>) => ({ ...base, ...data }))

vi.mock('../api/client', () => ({
  api: {
    settings: {
      get: vi.fn(async () => base),
      update: (...args: unknown[]) => update(...(args as [Record<string, unknown>])),
    },
    // P17.0: the API Keys tab embeds ExternalClientsPanel; P17.2: the MCP card
    // on the Integrations tab loads workspaces/projects + integrations.mcp.
    workspaces: { list: vi.fn(async () => []) },
    projects: { list: vi.fn(async () => []) },
    apiClients: { list: vi.fn(async () => []), create: vi.fn(), revoke: vi.fn() },
    integrations: {
      mcp: vi.fn(async () => ({
        server_name: 'agentboard', command: 'python', args: ['-m', 'app.mcp.server'],
        cwd: '/x/apps/api', capability_env: 'AGENTBOARD_MCP_CAPABILITY',
        read_tools: [], propose_tools: [],
      })),
      // P17.5: the GPT Actions card fetches the contract on the Integrations tab.
      gptOpenapi: vi.fn(async () => ({ openapi: '3.1.0', servers: [{ url: 'https://x/api/external/v1' }], paths: {} })),
    },
    // P17.3b: the Webhooks card lists subscriptions once a workspace is selected.
    webhooks: { list: vi.fn(async () => []) },
    // P18.2: the Backups card lists existing backups on mount.
    backups: { list: vi.fn(async () => []), create: vi.fn() },
  },
}))

describe('SettingsPanel', () => {
  it('renders loaded settings and the read-only ceiling status across tabs', async () => {
    render(<SettingsPanel />)
    // Integrations tab (default): email + external API ceiling
    expect(await screen.findByDisplayValue('approvo@localhost')).toBeTruthy()
    expect(screen.getByText('AGENTBOARD_EXTERNAL_API_ENABLED=true')).toBeTruthy()
    // Team & Access tab: LAN ceiling
    fireEvent.click(screen.getByRole('tab', { name: 'Team & Access' }))
    expect(screen.getByText('AGENTBOARD_LAN_MODE_ENABLED=true')).toBeTruthy()
    expect(screen.getByLabelText('Accept teammates from the LAN')).toBeTruthy()
  })

  it('saves the LAN switch when toggled (global Save works from the Team tab)', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByRole('tab', { name: 'Team & Access' }))
    fireEvent.click(screen.getByLabelText('Accept teammates from the LAN'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith({ lan_mode_active: true }))
  })

  it('saves the registration switch when closed (P16.2, D30)', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByRole('tab', { name: 'Team & Access' }))
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

  it('saves the backup switch (P18.2, D44)', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByLabelText('Enable backups'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith({ backup_enabled: true }))
  })

  it('relocates the external API keys panel into the API Keys tab (P17.0, D36)', async () => {
    render(<SettingsPanel />)
    await screen.findByDisplayValue('approvo@localhost')
    fireEvent.click(screen.getByRole('tab', { name: 'API Keys' }))
    // ExternalClientsPanel's own loopback exposure note proves it is embedded here.
    await waitFor(() => expect(screen.getByText(/disabled by default/i)).toBeTruthy())
    expect(screen.getByText(/loopback-bound/i)).toBeTruthy()
    // The global settings Save is hidden on this tab (no switches to save).
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })
})
