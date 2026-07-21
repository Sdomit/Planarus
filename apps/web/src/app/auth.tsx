import { createContext, useCallback, useContext, useEffect, useState, type ReactNode, type FormEvent } from 'react'
import { api, type AuthMe } from '../api/client'

/**
 * P11.3 — hosted/LAN sign-in surface.
 *
 * The auth API 404s when PLANARUS_AUTH_ENABLED is off, so:
 *   404 → "local" single-user mode: render the app exactly as before, no auth UI.
 *   401 → auth is on and nobody is signed in: show the sign-in gate.
 *   200 → signed in: render the app and expose `me` via context (sidebar chip).
 * Any other failure falls back to "local" — the panels surface their own errors.
 */
type AuthState = { kind: 'loading' } | { kind: 'local' } | { kind: 'anon' } | { kind: 'user'; me: AuthMe }

interface AuthContextValue {
  me: AuthMe | null
  signOut: () => void
}

const AuthContext = createContext<AuthContextValue>({ me: null, signOut: () => {} })

export function useAuthInfo(): AuthContextValue {
  return useContext(AuthContext)
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ kind: 'loading' })

  useEffect(() => {
    api.auth
      .me()
      .then((me) => setState({ kind: 'user', me }))
      .catch((e: Error) => {
        if (e.message.startsWith('401')) setState({ kind: 'anon' })
        else setState({ kind: 'local' }) // 404 (auth off) or unreachable
      })
  }, [])

  const signOut = useCallback(() => {
    // Reload after logout: drops every panel's in-memory state with the session.
    void api.auth.logout().finally(() => window.location.reload())
  }, [])

  if (state.kind === 'loading') return null
  if (state.kind === 'anon') return <SignIn onSignedIn={(me) => setState({ kind: 'user', me })} />
  if (state.kind === 'user' && state.me.password_must_change) {
    // P16.2: an admin-issued temp password only unlocks the auth surface —
    // force the rotation before the app (the API fences everything else anyway).
    return (
      <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', background: 'var(--bg-canvas)', padding: 'var(--space-4)' }}>
        <ChangePasswordForm
          forced
          onChanged={() => void api.auth.me().then((me) => setState({ kind: 'user', me }))}
        />
      </div>
    )
  }
  return (
    <AuthContext.Provider value={{ me: state.kind === 'user' ? state.me : null, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

function friendly(msg: string): string {
  if (msg.startsWith('400')) return 'Current password is incorrect.'
  if (msg.startsWith('401')) return 'Invalid email or password.'
  if (msg.startsWith('409')) return 'An account with this email already exists.'
  if (msg.startsWith('429')) return 'Too many attempts — wait a minute and try again.'
  if (msg.startsWith('404')) return 'Password sign-in is not enabled on this server.'
  if (msg.startsWith('422')) return 'Password must be at least 10 characters.'
  // client.ts prefixes every HTTP failure with its status, so a message without
  // one never reached the server: API down, wrong proxy target, dropped LAN
  // link. Browsers word that differently ("Failed to fetch", "Load failed",
  // "NetworkError…"), so key off the missing status rather than the wording.
  if (!/^\d{3}/.test(msg)) return 'Cannot reach the server. Is the API running?'
  return msg
}

/** P16.2 — rotate the caller's own password. Used forced (temp-password gate,
 * before the app renders) and voluntarily (Team view). Rotation signs out
 * every other session for the account. */
export function ChangePasswordForm({
  forced = false,
  onChanged,
}: {
  forced?: boolean
  onChanged: () => void
}) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    api.auth
      .passwordChange(current, next)
      .then(() => onChanged())
      .catch((err: Error) => setError(friendly(err.message)))
      .finally(() => setBusy(false))
  }

  return (
    <form className="card" onSubmit={submit} style={{ width: 'min(360px, 100%)', display: 'grid', gap: 'var(--space-4)' }}>
      <div>
        <h3 style={{ margin: 0 }}>{forced ? 'Set a new password' : 'Change password'}</h3>
        <p style={{ margin: '4px 0 0', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
          {forced
            ? 'Your temporary password must be replaced before you can continue.'
            : 'Every other session for your account will be signed out.'}
        </p>
      </div>
      <div className="form-field">
        <label className="form-label" htmlFor="chpw-current">{forced ? 'Temporary password' : 'Current password'}</label>
        <input
          id="chpw-current" className="input" type="password" autoComplete="current-password"
          value={current} onChange={(e) => setCurrent(e.target.value)} required
        />
      </div>
      <div className="form-field">
        <label className="form-label" htmlFor="chpw-next">New password</label>
        <input
          id="chpw-next" className="input" type="password" autoComplete="new-password" minLength={10}
          value={next} onChange={(e) => setNext(e.target.value)} required
        />
        <p style={{ margin: '4px 0 0', color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
          At least 10 characters — a long phrase beats a short scramble.
        </p>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <button type="submit" className="btn btn-solid" disabled={busy}>
        {busy ? 'Working…' : forced ? 'Set password' : 'Change password'}
      </button>
    </form>
  )
}

export function SignIn({ onSignedIn }: { onSignedIn: (me: AuthMe) => void }) {
  // First run: nobody has claimed the server yet, so open on the register form
  // and say what the account is about to become (D29). Stays false forever after.
  const [setup, setSetup] = useState(false)
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.auth
      .status()
      .then(({ needs_setup }) => {
        if (!needs_setup) return
        setSetup(true)
        setMode('register')
      })
      .catch(() => {}) // older server without /auth/status: plain sign-in
  }, [])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const call =
      mode === 'signin'
        ? api.auth.passwordLogin(email, password)
        : api.auth.passwordRegister(email, password, displayName.trim() || undefined)
    call
      .then(onSignedIn)
      .catch((err: Error) => setError(friendly(err.message)))
      .finally(() => setBusy(false))
  }

  return (
    <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', background: 'var(--bg-canvas)', padding: 'var(--space-4)' }}>
      <form className="card" onSubmit={submit} style={{ width: 'min(360px, 100%)', display: 'grid', gap: 'var(--space-4)' }}>
        <div>
          <h2 style={{ margin: 0 }}>{setup ? 'Set up Planarus' : 'Planarus'}</h2>
          <p style={{ margin: '4px 0 0', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
            {setup
              ? 'This first account becomes the server admin — it can add people and grant admin from Team.'
              : mode === 'signin'
                ? 'Sign in to your team workspace'
                : 'Create your account'}
          </p>
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="auth-email">Email</label>
          <input
            id="auth-email" className="input" type="email" autoComplete="email"
            value={email} onChange={(e) => setEmail(e.target.value)} required
          />
        </div>

        {mode === 'register' && (
          <div className="form-field">
            <label className="form-label" htmlFor="auth-name">Display name (optional)</label>
            <input
              id="auth-name" className="input" type="text" maxLength={200}
              value={displayName} onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
        )}

        <div className="form-field">
          <label className="form-label" htmlFor="auth-password">Password</label>
          <input
            id="auth-password" className="input" type="password"
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            minLength={mode === 'register' ? 10 : 1}
            value={password} onChange={(e) => setPassword(e.target.value)} required
          />
          {mode === 'register' && (
            <p style={{ margin: '4px 0 0', color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
              At least 10 characters — a long phrase beats a short scramble.
            </p>
          )}
        </div>

        {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}

        <button type="submit" className="btn btn-solid" disabled={busy}>
          {busy ? 'Working…' : setup ? 'Create admin account' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </button>

        {/* D54: there is no self-service reset (a reset mail has nowhere to go
            until outbound email ships), so the gate has to say what the two
            real routes are — otherwise a locked-out admin has no way back. */}
        {!setup && mode === 'signin' && (
          <p style={{ margin: 0, color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
            Forgotten it? An admin can reset your password from Team. If nobody
            can sign in, run <code>python -m app.jobs admin --reset-password YOU@EXAMPLE</code> on
            the machine hosting Planarus.
          </p>
        )}

        {/* No accounts exist during setup, so there is nothing to switch to. */}
        {!setup && (
          <button
            type="button" className="btn btn-ghost btn-sm"
            onClick={() => { setMode((m) => (m === 'signin' ? 'register' : 'signin')); setError(null) }}
          >
            {mode === 'signin' ? 'New here? Create an account' : 'Have an account? Sign in'}
          </button>
        )}
      </form>
    </div>
  )
}
