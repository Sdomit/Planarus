import { createContext, useCallback, useContext, useEffect, useState, type ReactNode, type FormEvent } from 'react'
import { api, type AuthMe } from '../api/client'

/**
 * P11.3 — hosted/LAN sign-in surface.
 *
 * The auth API 404s when AGENTBOARD_AUTH_ENABLED is off, so:
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
  return (
    <AuthContext.Provider value={{ me: state.kind === 'user' ? state.me : null, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

function friendly(msg: string): string {
  if (msg.startsWith('401')) return 'Invalid email or password.'
  if (msg.startsWith('409')) return 'An account with this email already exists.'
  if (msg.startsWith('429')) return 'Too many attempts — wait a minute and try again.'
  if (msg.startsWith('404')) return 'Password sign-in is not enabled on this server.'
  if (msg.startsWith('422')) return 'Password must be at least 10 characters.'
  return msg
}

export function SignIn({ onSignedIn }: { onSignedIn: (me: AuthMe) => void }) {
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg-base)', padding: 'var(--space-4)' }}>
      <form className="card" onSubmit={submit} style={{ width: 360, display: 'grid', gap: 'var(--space-4)' }}>
        <div>
          <h2 style={{ margin: 0 }}>Approvo</h2>
          <p style={{ margin: '4px 0 0', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
            {mode === 'signin' ? 'Sign in to your team workspace' : 'Create your account'}
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
          {busy ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </button>

        <button
          type="button" className="btn btn-ghost btn-sm"
          onClick={() => { setMode((m) => (m === 'signin' ? 'register' : 'signin')); setError(null) }}
        >
          {mode === 'signin' ? 'New here? Create an account' : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  )
}
