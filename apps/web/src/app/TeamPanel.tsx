import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  api,
  type AdminUser,
  type MemberCandidate,
  type MemberRead,
  type Workspace,
} from '../api/client'
import { ChangePasswordForm, useAuthInfo } from './auth'

/**
 * P16.2 — the Team surface (team mode only; the nav item is hidden in local
 * single-user mode).
 *
 * Everyone: their own account (with voluntary password change) and the member
 * roster of each workspace they belong to. Workspace owners additionally
 * manage membership and roles (the P10.1 members API finally gets a UI).
 * Server admins additionally manage accounts (the P16.1 admin plane): create
 * with a one-time temp password, reset, deactivate/reactivate, admin toggle.
 */

const ROLES = ['owner', 'editor', 'viewer'] as const
const ONLINE_WINDOW_MS = 2 * 60_000

function avatarHue(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360
  return h
}

function initialsOf(s: string): string {
  return (
    s.replace(/[^a-zA-Z0-9 ]/g, '').split(/\s+/).filter(Boolean).slice(0, 2)
      .map((w) => w[0]).join('').toUpperCase() || '?'
  )
}

function Avatar({ id, name }: { id: string; name: string }) {
  return (
    <span
      className="avatar avatar-sm"
      style={{ background: `hsl(${avatarHue(id)} 55% 42%)`, color: '#fff', flexShrink: 0 }}
      aria-hidden="true"
    >
      {initialsOf(name)}
    </span>
  )
}

function lastSeenLabel(iso: string | null): { label: string; online: boolean } {
  if (!iso) return { label: 'never signed in', online: false }
  const t = new Date(iso).getTime()
  if (isNaN(t)) return { label: iso, online: false }
  const ago = Date.now() - t
  if (ago < ONLINE_WINDOW_MS) return { label: 'online now', online: true }
  const mins = Math.round(ago / 60_000)
  if (mins < 60) return { label: `seen ${mins}m ago`, online: false }
  const hours = Math.round(mins / 60)
  if (hours < 48) return { label: `seen ${hours}h ago`, online: false }
  return { label: `seen ${Math.round(hours / 24)}d ago`, online: false }
}

function chip(text: string, tone: 'accent' | 'danger' | 'muted' = 'muted') {
  const colors = {
    accent: { background: 'var(--accent-muted)', color: 'var(--text-accent)' },
    danger: { background: 'var(--status-danger-bg, #fee)', color: 'var(--status-danger-fg, #b00)' },
    muted: { background: 'var(--bg-subtle)', color: 'var(--text-secondary)' },
  }[tone]
  return (
    <span style={{ ...colors, borderRadius: 999, padding: '1px 8px', fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap' }}>
      {text}
    </span>
  )
}

// One-time temp-password reveal — same contract as the API-key modal: shown
// once, never persisted by the client.
function TempPasswordModal({
  title, password, note, onClose,
}: { title: string; password: string; note?: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const doneRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    doneRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const copy = () => {
    void navigator.clipboard?.writeText(password).then(
      () => setCopied(true),
      () => setCopied(false),
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="temp-pw-title">
        <div className="modal-header">
          <span className="modal-title" id="temp-pw-title">{title}</span>
        </div>
        <div className="modal-body">
          <p style={{ color: 'var(--status-warning-fg)', fontSize: 'var(--text-sm)', marginTop: 0 }}>
            Hand this temporary password to the person now — it is shown{' '}
            <strong>only once</strong>. They must replace it at first sign-in.
          </p>
          <code style={{
            display: 'block', wordBreak: 'break-all',
            background: 'var(--bg-subtle)', border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)', padding: 'var(--space-3)',
            fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)',
            margin: 'var(--space-3) 0',
          }}>{password}</code>
          {note && (
            <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
              {note}
            </p>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-outline btn-sm" onClick={copy}>
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
          <button ref={doneRef} type="button" className="btn btn-solid btn-sm" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}

// --- accounts section (server admins) ----------------------------------------
function AccountsSection({
  selfId, ownedWorkspaces, onGranted,
}: { selfId: string; ownedWorkspaces: Workspace[]; onGranted: () => void }) {
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [grantWs, setGrantWs] = useState('')
  const [grantRole, setGrantRole] = useState<string>('editor')
  const [reveal, setReveal] = useState<
    { title: string; password: string; note?: string } | null
  >(null)

  const load = useCallback(() => {
    api.admin.users().then(setUsers).catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const run = (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    fn()
      .then(load)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api.admin.createUser(email.trim(), name.trim() || undefined)
      // The account exists from here on, so the temp password is revealed even if
      // the optional grant below fails — it is the only copy, and swallowing it
      // would force a reset. The grant goes through the members API as the acting
      // admin, so D29 holds: admin authority still never reaches into workspaces.
      let note: string | undefined
      if (grantWs) {
        const wsName = ownedWorkspaces.find((w) => w.id === grantWs)?.name ?? 'the workspace'
        try {
          await api.members.add(grantWs, res.user.email, grantRole)
          note = `Added to ${wsName} as ${grantRole}.`
          onGranted()
        } catch (err) {
          note = `Account created, but the ${wsName} grant failed (${(err as Error).message}). Add them from the workspace section below.`
        }
      }
      setReveal({
        title: `Account created — ${res.user.email}`,
        password: res.temp_password,
        note,
      })
      setCreating(false)
      setEmail('')
      setName('')
      setGrantWs('')
      load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const resetPw = (u: AdminUser) => {
    if (!window.confirm(`Reset the password for ${u.email}? Every session for the account will be signed out.`)) return
    setBusy(true)
    setError(null)
    api.admin
      .resetPassword(u.id)
      .then((res) => setReveal({ title: `Password reset — ${u.email}`, password: res.temp_password }))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  return (
    <section className="card" style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <h3 style={{ margin: 0, flex: 1 }}>Accounts</h3>
        <button type="button" className="btn btn-solid btn-sm" onClick={() => setCreating(v => !v)}>
          {creating ? 'Cancel' : 'Add user'}
        </button>
      </div>
      <p style={{ margin: 0, color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
        Every account on this server. Admin governs accounts only — project access
        still comes from workspace membership below.
      </p>

      {creating && (
        <form onSubmit={create} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end' }}>
          <div className="form-field" style={{ flex: '1 1 200px', margin: 0 }}>
            <label className="form-label" htmlFor="acct-email">Email</label>
            <input id="acct-email" className="input input-sm" type="email" required
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="form-field" style={{ flex: '1 1 160px', margin: 0 }}>
            <label className="form-label" htmlFor="acct-name">Display name (optional)</label>
            <input id="acct-name" className="input input-sm" type="text" maxLength={200}
              value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {ownedWorkspaces.length > 0 && (
            <div className="form-field" style={{ flex: '1 1 160px', margin: 0 }}>
              <label className="form-label" htmlFor="acct-ws">Workspace access</label>
              <select id="acct-ws" className="input input-sm" value={grantWs}
                onChange={(e) => setGrantWs(e.target.value)}>
                <option value="">None — add later</option>
                {ownedWorkspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
            </div>
          )}
          {grantWs && (
            <div className="form-field" style={{ margin: 0 }}>
              <label className="form-label" htmlFor="acct-role">Role</label>
              <select id="acct-role" className="input input-sm" value={grantRole}
                onChange={(e) => setGrantRole(e.target.value)}>
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          )}
          <button type="submit" className="btn btn-solid btn-sm" disabled={busy}>Create</button>
        </form>
      )}

      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      {!users && !error && <p style={{ margin: 0, color: 'var(--text-tertiary)' }}>Loading…</p>}

      {users && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {users.map((u) => {
            const seen = lastSeenLabel(u.last_seen_at)
            return (
              <li key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 4px', borderTop: '1px solid var(--border-default)', opacity: u.is_active ? 1 : 0.55 }}>
                <Avatar id={u.id} name={u.display_name || u.email} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {u.display_name}
                    </span>
                    {u.id === selfId && chip('you', 'accent')}
                    {u.is_admin && chip('admin', 'accent')}
                    {!u.is_active && chip('deactivated', 'danger')}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.email}</span>
                    <span aria-hidden="true">·</span>
                    {seen.online && <span className="live-dot" title="Online now" />}
                    <span>{seen.label}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <button type="button" className="btn btn-ghost btn-xs" disabled={busy}
                    onClick={() => resetPw(u)}>Reset password</button>
                  <button type="button" className="btn btn-ghost btn-xs" disabled={busy}
                    onClick={() => run(() => api.admin.setAdmin(u.id, !u.is_admin))}>
                    {u.is_admin ? 'Remove admin' : 'Make admin'}
                  </button>
                  {u.is_active ? (
                    <button type="button" className="btn btn-ghost btn-xs" disabled={busy}
                      onClick={() => {
                        if (window.confirm(`Deactivate ${u.email}? They are signed out everywhere and cannot sign in until reactivated.`)) {
                          run(() => api.admin.deactivate(u.id))
                        }
                      }}>Deactivate</button>
                  ) : (
                    <button type="button" className="btn btn-ghost btn-xs" disabled={busy}
                      onClick={() => run(() => api.admin.reactivate(u.id))}>Reactivate</button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {reveal && (
        <TempPasswordModal title={reveal.title} password={reveal.password} note={reveal.note}
          onClose={() => setReveal(null)} />
      )}
    </section>
  )
}

// --- one workspace's members --------------------------------------------------
function WorkspaceMembers({
  workspace, myRole, selfId,
}: { workspace: Workspace; myRole: string; selfId: string }) {
  const [members, setMembers] = useState<MemberRead[] | null>(null)
  const [candidates, setCandidates] = useState<MemberCandidate[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<string>('editor')
  const isOwner = myRole === 'owner'

  const load = useCallback(() => {
    api.members.list(workspace.id).then(setMembers).catch((e: Error) => setError(e.message))
    // Owner-only endpoint; everyone else sees the roster without the add form.
    // Failure is silent on purpose — the pick-list is a convenience, and typing
    // the address by hand still works.
    if (isOwner) api.members.candidates(workspace.id).then(setCandidates).catch(() => setCandidates([]))
  }, [workspace.id, isOwner])
  useEffect(load, [load])

  const run = (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    fn()
      .then(load)
      .catch((e: Error) => {
        setError(e.message.startsWith('404')
          ? 'No account with that email yet — they must sign in once first, or an admin can create the account.'
          : e.message)
      })
      .finally(() => setBusy(false))
  }

  const add = (e: FormEvent) => {
    e.preventDefault()
    run(() => api.members.add(workspace.id, email.trim(), role))
    setEmail('')
  }

  return (
    <section className="card" style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <h3 style={{ margin: 0 }}>
        {workspace.name}{' '}
        <span style={{ fontWeight: 400, fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>
          — members · your role: {myRole}
        </span>
      </h3>

      {isOwner && (
        <form onSubmit={add} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end' }}>
          <div className="form-field" style={{ flex: '1 1 200px', margin: 0 }}>
            <label className="form-label" htmlFor={`add-${workspace.id}`}>Add member by email</label>
            <input id={`add-${workspace.id}`} className="input input-sm" type="email" required
              list={`cand-${workspace.id}`} autoComplete="off"
              value={email} onChange={(e) => setEmail(e.target.value)} />
            {/* Native datalist: the browser does matching, keyboard nav and the
                mobile keyboard for free. Typing an address that isn't listed
                still submits — which is what you want when inviting someone
                who has an account you can't see, and the 404 explains itself. */}
            <datalist id={`cand-${workspace.id}`}>
              {candidates.map((c) => (
                <option key={c.email} value={c.email}>{c.display_name}</option>
              ))}
            </datalist>
          </div>
          <label className="form-label" style={{ display: 'grid', gap: 4 }}>
            Role
            <select className="input input-sm" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
          <button type="submit" className="btn btn-solid btn-sm" disabled={busy}>Add</button>
        </form>
      )}

      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      {!members && !error && <p style={{ margin: 0, color: 'var(--text-tertiary)' }}>Loading…</p>}

      {members && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {members.map((m) => (
            <li key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 4px', borderTop: '1px solid var(--border-default)' }}>
              <Avatar id={m.user_id} name={m.display_name || m.email} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{m.display_name}</span>
                  {m.user_id === selfId && chip('you', 'accent')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.email}</div>
              </div>
              {isOwner ? (
                <>
                  <select
                    className="input input-sm" style={{ width: 'auto' }} value={m.role} disabled={busy}
                    aria-label={`Role for ${m.email}`}
                    onChange={(e) => run(() => api.members.setRole(workspace.id, m.user_id, e.target.value))}
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button type="button" className="btn btn-ghost btn-xs" disabled={busy}
                    onClick={() => {
                      if (window.confirm(`Remove ${m.email} from ${workspace.name}?`)) {
                        run(() => api.members.remove(workspace.id, m.user_id))
                      }
                    }}>Remove</button>
                </>
              ) : (
                chip(m.role)
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// --- workspaces auth left ownerless (server admin only) -----------------------
function UnclaimedWorkspaces({ selfEmail, onClaimed }: { selfEmail: string; onClaimed: () => void }) {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.admin.unclaimedWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]))
  }, [])
  useEffect(load, [load])

  const claim = (ws: Workspace) => {
    setBusyId(ws.id)
    setError(null)
    api.members.add(ws.id, selfEmail, 'owner')
      .then(() => { load(); onClaimed() })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusyId(null))
  }

  // Turning auth on for the first time on a server that already had local-mode
  // data leaves every existing workspace with no members at all — invisible to
  // its own admin (D30's membership scoping applies uniformly). This is the
  // only place that gap is surfaced; without it there is no UI path to it.
  if (!workspaces || workspaces.length === 0) return null

  return (
    <section className="card" style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <h3 style={{ margin: 0 }}>Unclaimed workspaces</h3>
      <p style={{ margin: 0, color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
        These existed before sign-in was turned on and have no owner yet — claim
        one to see its projects.
      </p>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
        {workspaces.map((ws) => (
          <li key={ws.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ flex: 1 }}>{ws.name}</span>
            <button type="button" className="btn btn-solid btn-sm" disabled={busyId === ws.id}
              onClick={() => claim(ws)}>
              {busyId === ws.id ? 'Claiming…' : 'Claim as owner'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

// --- the panel ----------------------------------------------------------------
export default function TeamPanel() {
  const { me } = useAuthInfo()
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [changingPw, setChangingPw] = useState(false)
  const [pwChanged, setPwChanged] = useState(false)
  // Bumped when Accounts grants membership, to remount the roster below so the
  // new member shows immediately. ponytail: remount over per-section refetch
  // plumbing — a LAN server has a handful of workspaces.
  const [rosterKey, setRosterKey] = useState(0)

  useEffect(() => {
    if (!me) return
    api.workspaces.list().then(setWorkspaces).catch(() => setWorkspaces([]))
  }, [me])

  if (!me) {
    return (
      <p style={{ color: 'var(--text-tertiary)' }}>
        Team mode is off — this is a local single-user workspace.
      </p>
    )
  }

  const roleFor = (wsId: string) =>
    me.memberships.find((m) => m.workspace_id === wsId)?.role ?? null

  return (
    <div style={{ display: 'grid', gap: 'var(--space-5)', maxWidth: 720 }}>
      <section className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Avatar id={me.user.id} name={me.user.display_name || me.user.email} />
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontWeight: 600 }}>{me.user.display_name}</span>
            {me.user.is_admin && chip('admin', 'accent')}
          </div>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>{me.user.email}</div>
        </div>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => { setChangingPw(v => !v); setPwChanged(false) }}>
          {changingPw ? 'Cancel' : 'Change password'}
        </button>
        {pwChanged && <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>Password changed ✓</span>}
        {changingPw && (
          <div style={{ flexBasis: '100%' }}>
            <ChangePasswordForm onChanged={() => { setChangingPw(false); setPwChanged(true) }} />
          </div>
        )}
      </section>

      {me.user.is_admin && (
        <UnclaimedWorkspaces
          selfEmail={me.user.email}
          // me.memberships is set once at sign-in — a partial refetch here
          // would still leave the freshly-claimed workspace missing from it,
          // so the roster below wouldn't render. Same fix signOut already
          // uses: reload, and every panel picks up the new /auth/me.
          onClaimed={() => window.location.reload()}
        />
      )}

      {me.user.is_admin && (
        <AccountsSection
          selfId={me.user.id}
          ownedWorkspaces={(workspaces ?? []).filter((ws) => roleFor(ws.id) === 'owner')}
          onGranted={() => setRosterKey((n) => n + 1)}
        />
      )}

      {workspaces === null && <p style={{ color: 'var(--text-tertiary)' }}>Loading workspaces…</p>}
      {workspaces?.map((ws) => {
        const myRole = roleFor(ws.id)
        if (!myRole) return null
        return <WorkspaceMembers key={`${ws.id}:${rosterKey}`} workspace={ws} myRole={myRole} selfId={me.user.id} />
      })}
    </div>
  )
}
