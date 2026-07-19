import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import TeamPanel from './TeamPanel'
import { api, type AuthMe } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    admin: {
      users: vi.fn(),
      createUser: vi.fn(),
      resetPassword: vi.fn(),
      deactivate: vi.fn(),
      reactivate: vi.fn(),
      setAdmin: vi.fn(),
    },
    members: { list: vi.fn(), add: vi.fn(), setRole: vi.fn(), remove: vi.fn() },
    workspaces: { list: vi.fn() },
    auth: { passwordChange: vi.fn() },
  },
}))

// TeamPanel reads the signed-in user from the auth context; swap it per test.
let currentMe: AuthMe | null = null
vi.mock('./auth', () => ({
  useAuthInfo: () => ({ me: currentMe, signOut: vi.fn() }),
  ChangePasswordForm: () => <div>change-password-form</div>,
}))

const ADMIN_ME: AuthMe = {
  user: {
    id: 'usr_admin', email: 'root@team.lan', display_name: 'Root',
    is_active: true, is_admin: true, created_at: 't', updated_at: 't',
  },
  memberships: [{ workspace_id: 'ws_1', role: 'owner' }],
  password_must_change: false,
}

const PLAIN_ME: AuthMe = {
  ...ADMIN_ME,
  user: { ...ADMIN_ME.user, id: 'usr_plain', email: 'pat@team.lan', display_name: 'Pat', is_admin: false },
  memberships: [{ workspace_id: 'ws_1', role: 'viewer' }],
}

const ROSTER = [
  {
    id: 'usr_admin', email: 'root@team.lan', display_name: 'Root',
    is_admin: true, is_active: true, created_at: 't',
    last_seen_at: new Date().toISOString(), memberships: [{ workspace_id: 'ws_1', role: 'owner' }],
  },
  {
    id: 'usr_2', email: 'sam@team.lan', display_name: 'Sam',
    is_admin: false, is_active: false, created_at: 't',
    last_seen_at: null, memberships: [],
  },
]

const MEMBERS = [
  {
    id: 'wsm_1', workspace_id: 'ws_1', user_id: 'usr_admin', email: 'root@team.lan',
    display_name: 'Root', role: 'owner', created_at: 't', updated_at: 't',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.workspaces.list).mockResolvedValue([
    { id: 'ws_1', name: 'Studio', slug: 'studio' } as never,
  ])
  vi.mocked(api.members.list).mockResolvedValue(MEMBERS)
  vi.mocked(api.admin.users).mockResolvedValue(ROSTER)
})

afterEach(cleanup)

describe('TeamPanel', () => {
  it('shows the admin accounts roster with badges and online state', async () => {
    currentMe = ADMIN_ME
    render(<TeamPanel />)
    expect(await screen.findByText('Accounts')).toBeTruthy()
    expect(await screen.findByText('Sam')).toBeTruthy()
    expect(screen.getByText('deactivated')).toBeTruthy()
    expect(screen.getByText('online now')).toBeTruthy()
    expect(screen.getByText('never signed in')).toBeTruthy()
    // owner controls on the workspace section
    expect(await screen.findByLabelText('Add member by email')).toBeTruthy()
  })

  it('creates an account and reveals the temp password exactly once', async () => {
    currentMe = ADMIN_ME
    vi.mocked(api.admin.createUser).mockResolvedValue({
      user: ROSTER[1] as never,
      temp_password: 'one-time-secret-pw',
    })
    render(<TeamPanel />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add user' }))
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'sam@team.lan' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByText('one-time-secret-pw')).toBeTruthy()
    await waitFor(() =>
      expect(api.admin.createUser).toHaveBeenCalledWith('sam@team.lan', undefined),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.queryByText('one-time-secret-pw')).toBeNull()
  })

  it('hides account administration from non-admins', async () => {
    currentMe = PLAIN_ME
    render(<TeamPanel />)
    // workspace roster still renders (viewer: read-only, no owner controls)
    expect(await screen.findByText(/members · your role: viewer/)).toBeTruthy()
    expect(screen.queryByText('Accounts')).toBeNull()
    expect(screen.queryByLabelText('Add member by email')).toBeNull()
    expect(api.admin.users).not.toHaveBeenCalled()
  })
})
