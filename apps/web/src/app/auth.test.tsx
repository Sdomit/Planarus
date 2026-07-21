import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { AuthGate } from './auth'
import { api, type AuthMe } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    auth: {
      me: vi.fn(),
      status: vi.fn(),
      passwordLogin: vi.fn(),
      passwordRegister: vi.fn(),
      logout: vi.fn(),
      passwordChange: vi.fn(),
    },
  },
}))

const ME: AuthMe = {
  user: {
    id: 'usr_1', email: 'pat@team.lan', display_name: 'Pat',
    is_active: true, created_at: 't', updated_at: 't',
  },
  memberships: [{ workspace_id: 'ws_1', role: 'owner' }],
}

beforeEach(() => {
  vi.clearAllMocks()
  // Default: a server someone already claimed, so the gate is a plain sign-in.
  vi.mocked(api.auth.status).mockResolvedValue({ needs_setup: false })
})
afterEach(cleanup)

describe('AuthGate', () => {
  it('renders the app unchanged in local mode (auth surface 404s)', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('404: not found'))
    render(<AuthGate><p>the app</p></AuthGate>)
    expect(await screen.findByText('the app')).toBeTruthy()
    expect(screen.queryByLabelText('Email')).toBeNull()
  })

  it('renders the app directly when already signed in', async () => {
    vi.mocked(api.auth.me).mockResolvedValue(ME)
    render(<AuthGate><p>the app</p></AuthGate>)
    expect(await screen.findByText('the app')).toBeTruthy()
  })

  it('gates with the sign-in form on 401 and signs in', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
    vi.mocked(api.auth.passwordLogin).mockResolvedValue(ME)
    render(<AuthGate><p>the app</p></AuthGate>)

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'pat@team.lan' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct horse battery' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('the app')).toBeTruthy()
    expect(api.auth.passwordLogin).toHaveBeenCalledWith('pat@team.lan', 'correct horse battery')
  })

  it('shows a friendly error on bad credentials', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
    vi.mocked(api.auth.passwordLogin).mockRejectedValue(new Error('401: invalid email or password'))
    render(<AuthGate><p>the app</p></AuthGate>)

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'pat@team.lan' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong password 42' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('Invalid email or password.')).toBeTruthy()
    expect(screen.queryByText('the app')).toBeNull()
  })

  it('says the server is unreachable instead of leaking the browser string', async () => {
    // A dead API rejects with the browser's own TypeError — no status prefix.
    // Wording differs per browser, so both forms must map to the same message.
    for (const raw of ['Failed to fetch', 'Load failed']) {
      vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
      vi.mocked(api.auth.passwordLogin).mockRejectedValue(new TypeError(raw))
      render(<AuthGate><p>the app</p></AuthGate>)

      fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'pat@team.lan' } })
      fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct horse battery' } })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

      expect(await screen.findByText('Cannot reach the server. Is the API running?')).toBeTruthy()
      expect(screen.queryByText(raw)).toBeNull()
      cleanup()
    }
  })

  it('tells a locked-out user how to get back in, but not during setup', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
    render(<AuthGate><p>the app</p></AuthGate>)
    // Sign-in: both routes are named (ask an admin, or the recovery CLI).
    expect(await screen.findByText(/An admin can reset your password/)).toBeTruthy()
    expect(screen.getByText(/--reset-password/)).toBeTruthy()
    cleanup()

    // Setup: there are no admins and no accounts yet, so the advice is noise.
    vi.mocked(api.auth.status).mockResolvedValue({ needs_setup: true })
    render(<AuthGate><p>the app</p></AuthGate>)
    expect(await screen.findByText('Set up Planarus')).toBeTruthy()
    expect(screen.queryByText(/An admin can reset your password/)).toBeNull()
  })

  it('registers via the create-account mode', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
    vi.mocked(api.auth.passwordRegister).mockResolvedValue(ME)
    render(<AuthGate><p>the app</p></AuthGate>)

    fireEvent.click(await screen.findByRole('button', { name: 'New here? Create an account' }))
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@team.lan' } })
    fireEvent.change(screen.getByLabelText('Display name (optional)'), { target: { value: 'Newbie' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a long enough phrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('the app')).toBeTruthy()
    await waitFor(() =>
      expect(api.auth.passwordRegister).toHaveBeenCalledWith('new@team.lan', 'a long enough phrase', 'Newbie'),
    )
  })

  it('opens in setup mode on an unclaimed server (D29)', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
    vi.mocked(api.auth.status).mockResolvedValue({ needs_setup: true })
    vi.mocked(api.auth.passwordRegister).mockResolvedValue(ME)
    render(<AuthGate><p>the app</p></AuthGate>)

    // Register form up front, no toggle back to a sign-in nobody can use.
    expect(await screen.findByText('Set up Planarus')).toBeTruthy()
    expect(screen.getByLabelText('Display name (optional)')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'New here? Create an account' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'root@team.lan' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a long enough phrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create admin account' }))
    expect(await screen.findByText('the app')).toBeTruthy()
  })

  it('forces the change-password screen on a temp password (P16.2)', async () => {
    vi.mocked(api.auth.me)
      .mockResolvedValueOnce({ ...ME, password_must_change: true })
      .mockResolvedValueOnce(ME) // refetch after the rotation
    vi.mocked(api.auth.passwordChange).mockResolvedValue(undefined)
    render(<AuthGate><p>the app</p></AuthGate>)

    // The app is withheld until the temp password is replaced.
    expect(await screen.findByText('Set a new password')).toBeTruthy()
    expect(screen.queryByText('the app')).toBeNull()

    fireEvent.change(screen.getByLabelText('Temporary password'), { target: { value: 'temp-pass-123' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'a long enough phrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Set password' }))

    expect(await screen.findByText('the app')).toBeTruthy()
    expect(api.auth.passwordChange).toHaveBeenCalledWith('temp-pass-123', 'a long enough phrase')
  })

  it('explains a 409 on register', async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error('401: authentication required'))
    vi.mocked(api.auth.passwordRegister).mockRejectedValue(
      new Error('409: an account with this email already exists'),
    )
    render(<AuthGate><p>the app</p></AuthGate>)

    fireEvent.click(await screen.findByRole('button', { name: 'New here? Create an account' }))
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'pat@team.lan' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a long enough phrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('An account with this email already exists.')).toBeTruthy()
  })
})
