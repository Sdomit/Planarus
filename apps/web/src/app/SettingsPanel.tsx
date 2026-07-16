import { useEffect, useState } from 'react'
import { api, type AppSettings } from '../api/client'

// Phase 9B settings surface. Switch tier is editable; the env ceiling is shown
// read-only and always wins — a toggle here can never widen exposure.
export default function SettingsPanel() {
  const [s, setS] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.settings.get()
      .then(setS)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const patch = (next: Partial<AppSettings>) => {
    setS(prev => (prev ? { ...prev, ...next } : prev))
    setSaved(false)
  }

  const save = () => {
    if (!s) return
    setSaving(true); setError(null)
    api.settings
      .update({
        email_enabled: s.email_enabled,
        email_from: s.email_from,
        external_api_active: s.external_api_active,
      })
      .then(fresh => { setS(fresh); setSaved(true) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false))
  }

  if (loading) return <p style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
  if (!s) return <p className="form-error" role="alert">{error ?? 'Failed to load settings.'}</p>

  const yn = (b: boolean) => (b ? 'Yes' : 'No')

  return (
    <div className="card" style={{ maxWidth: 560, display: 'grid', gap: 'var(--space-6)' }}>
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

      {error && <p className="form-error" role="alert">{error}</p>}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button type="button" className="btn btn-solid btn-sm" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved && <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>Saved ✓</span>}
      </div>
    </div>
  )
}
