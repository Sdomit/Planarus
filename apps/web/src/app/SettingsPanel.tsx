import { useEffect, useState } from 'react'
import { api, type AppSettings, type AppSettingsUpdate } from '../api/client'
import ExternalClientsPanel from './ExternalClientsPanel'
import RestApiCard from './RestApiCard'
import McpCard from './McpCard'
import GptActionsCard from './GptActionsCard'
import RecipesCard from './RecipesCard'

const SWITCH_KEYS = ['email_enabled', 'email_from', 'external_api_active', 'lan_mode_active', 'registration_open'] as const

// P17.0: Settings is the integration hub's front door. Connectors/wiring live
// under Integrations + API Keys; team access under its own tab. The switch tier
// is editable; the env ceiling is shown read-only and always wins — a toggle
// here can never widen exposure. Save is global across tabs (only changed keys
// are sent), so tabs are pure presentation over one shared state.
type SettingsTab = 'integrations' | 'apikeys' | 'access'

const TABS: { key: SettingsTab; label: string }[] = [
  { key: 'integrations', label: 'Integrations' },
  { key: 'apikeys', label: 'API Keys' },
  { key: 'access', label: 'Team & Access' },
]

export default function SettingsPanel() {
  const [tab, setTab] = useState<SettingsTab>('integrations')
  const [s, setS] = useState<AppSettings | null>(null)
  // Last server state — Save sends only keys the user actually changed, so an
  // untouched switch never gets pinned into a DB row (env default stays live).
  const [initial, setInitial] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.settings.get()
      .then(data => { setS(data); setInitial(data) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const patch = (next: Partial<AppSettings>) => {
    setS(prev => (prev ? { ...prev, ...next } : prev))
    setSaved(false)
  }

  const save = () => {
    if (!s || !initial) return
    const changed: AppSettingsUpdate = {}
    for (const k of SWITCH_KEYS) {
      if (s[k] !== initial[k]) (changed as Record<string, unknown>)[k] = s[k]
    }
    if (Object.keys(changed).length === 0) { setSaved(true); return }
    setSaving(true); setError(null)
    api.settings
      .update(changed)
      .then(fresh => { setS(fresh); setInitial(fresh); setSaved(true) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false))
  }

  if (loading) return <p style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
  if (!s) return <p className="form-error" role="alert">{error ?? 'Failed to load settings.'}</p>

  const yn = (b: boolean) => (b ? 'Yes' : 'No')

  return (
    <div style={{ maxWidth: 640, display: 'grid', gap: 'var(--space-5)' }}>
      <div className="tabs" role="tablist" aria-label="Settings sections">
        {TABS.map(t => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`tab${tab === t.key ? ' active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'integrations' && (
        <div className="card" style={{ display: 'grid', gap: 'var(--space-6)' }}>
          <section>
            <h3 style={{ marginTop: 0 }}>External API</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 8px' }}>
              Online exposure permitted by environment:{' '}
              <strong>{yn(s.external_api_permitted_by_env)}</strong> · Extra hosts configured:{' '}
              <strong>{yn(s.external_api_hosts_configured)}</strong>
            </p>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={s.external_api_active}
                onChange={e => patch({ external_api_active: e.target.checked })}
              />
              <span>External API active</span>
            </label>
            {!s.external_api_permitted_by_env && (
              <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
                Inert until <code>AGENTBOARD_EXTERNAL_API_ENABLED=true</code> is set in the
                environment. This switch can only turn a permitted feature off — never widen exposure.
              </p>
            )}
          </section>

          <RestApiCard active={s.external_api_active} permitted={s.external_api_permitted_by_env} />

          <McpCard />

          <GptActionsCard
            active={s.external_api_active}
            permitted={s.external_api_permitted_by_env}
            hostsConfigured={s.external_api_hosts_configured}
          />

          <RecipesCard />

          <section>
            <h3 style={{ marginTop: 0 }}>Email reminders</h3>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={s.email_enabled}
                onChange={e => patch({ email_enabled: e.target.checked })}
              />
              <span>Send email reminders</span>
            </label>
            <div className="form-field" style={{ marginTop: 'var(--space-3)' }}>
              <label className="form-label" htmlFor="set-email-from">From address</label>
              <input
                id="set-email-from"
                className="input"
                type="email"
                value={s.email_from}
                onChange={e => patch({ email_from: e.target.value })}
              />
            </div>
            <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
              SMTP host is loopback-guarded by the environment (Mailpit):{' '}
              <strong>{yn(s.email_smtp_loopback)}</strong>. Remote SMTP is never sent to.
            </p>
          </section>
        </div>
      )}

      {tab === 'apikeys' && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>API keys</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-4)' }}>
            Machine keys for the external REST API &amp; MCP — scoped read / propose access only,
            never approve or apply. Relocated here from the main navigation (P17.0).
          </p>
          <ExternalClientsPanel />
        </div>
      )}

      {tab === 'access' && (
        <div className="card" style={{ display: 'grid', gap: 'var(--space-6)' }}>
          <section>
            <h3 style={{ marginTop: 0 }}>LAN team mode</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 8px' }}>
              Permitted by environment: <strong>{yn(s.lan_permitted_by_env)}</strong> · LAN hosts
              configured: <strong>{yn(s.lan_hosts_configured)}</strong> · Sign-in enabled:{' '}
              <strong>{yn(s.auth_enabled_by_env)}</strong> · Password provider:{' '}
              <strong>{yn(s.auth_password_enabled_by_env)}</strong>
            </p>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={s.lan_mode_active}
                onChange={e => patch({ lan_mode_active: e.target.checked })}
              />
              <span>Accept teammates from the LAN</span>
            </label>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 'var(--space-2)' }}>
              <input
                type="checkbox"
                checked={s.registration_open}
                onChange={e => patch({ registration_open: e.target.checked })}
              />
              <span>Accept self-registration on the sign-in screen</span>
            </label>
            <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
              Uncheck after onboarding — admins can still create accounts from the
              Team view (each new account gets a one-time temporary password).
            </p>
            {s.lan_permitted_by_env ? (
              <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
                ⚠ LAN traffic is plain HTTP — <strong>unencrypted on your local network</strong> (an
                accepted, documented tradeoff). Unchecking pauses LAN access immediately without a
                restart; it never affects this machine&apos;s own loopback access. Setup:{' '}
                <code>docs/guide/lan-team-mode.md</code>.
              </p>
            ) : (
              <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
                Inert until <code>AGENTBOARD_LAN_MODE_ENABLED=true</code> (plus sign-in and LAN hosts)
                is set in the environment — see <code>docs/guide/lan-team-mode.md</code>. This switch
                can only pause a permitted LAN — never widen exposure.
              </p>
            )}
          </section>
        </div>
      )}

      {tab !== 'apikeys' && (
        <>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button type="button" className="btn btn-solid btn-sm" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            {saved && <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>Saved ✓</span>}
          </div>
        </>
      )}
    </div>
  )
}
