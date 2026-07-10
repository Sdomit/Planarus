import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type EmailLogEntry,
  type NotificationRule,
  type ReminderSendResult,
} from '../api/client'
import { fmtTimestamp } from './format'
import { StatusBadge } from './StatusBadge'

export default function RemindersPanel({ projectId }: { projectId: string }) {
  const [rules, setRules] = useState<NotificationRule[]>([])
  const [log, setLog] = useState<EmailLogEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [trigger, setTrigger] = useState('due_soon')
  const [threshold, setThreshold] = useState(48)
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<ReminderSendResult | null>(null)

  const reload = useCallback(() => {
    Promise.all([api.notificationRules.list(projectId), api.reminders.emailLog(projectId)])
      .then(([r, l]) => {
        setRules(r)
        setLog(l)
      })
      .catch((e: Error) => setError(e.message))
  }, [projectId])

  useEffect(() => {
    setResult(null)
    setError(null)
    reload()
  }, [reload])

  const addRule = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return
    setSaving(true)
    setError(null)
    // Number('') is 0 when the field is cleared — clamp into the valid range.
    const windowHours = Math.min(720, Math.max(1, threshold || 48))
    api.notificationRules
      .create(projectId, { to_email: email.trim(), trigger_type: trigger, threshold_hours: windowHours })
      .then(() => {
        setEmail('')
        reload()
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false))
  }

  const toggle = (rule: NotificationRule) => {
    api.notificationRules
      .update(rule.id, { enabled: !rule.enabled })
      .then(reload)
      .catch((e: Error) => setError(e.message))
  }

  const sendNow = () => {
    setSending(true)
    setError(null)
    setResult(null)
    api.reminders
      .send(projectId)
      .then((res) => {
        setResult(res)
        reload()
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSending(false))
  }

  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <div className="card" style={{ padding: 'var(--space-5)' }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Email reminders</div>
        <p style={{ margin: '0 0 12px', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          Local-only: sends go to a loopback SMTP sink (Mailpit) and only when
          <code> AGENTBOARD_EMAIL_ENABLED=true</code>. There is no scheduler — use “Send now”.
        </p>

        <form onSubmit={addRule} style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-field" style={{ flex: 1, minWidth: 200 }}>
            <label className="form-label" htmlFor="rp-email">Send to</label>
            <input id="rp-email" className="input" type="email" placeholder="you@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="rp-trigger">Trigger</label>
            <select id="rp-trigger" className="input select" value={trigger} onChange={(e) => setTrigger(e.target.value)}>
              <option value="due_soon">due soon</option>
              <option value="daily_digest">daily digest</option>
            </select>
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="rp-threshold">Window (h)</label>
            <input id="rp-threshold" className="input" type="number" min={1} max={720} style={{ width: 90 }}
              value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
          </div>
          <button type="submit" className="btn btn-solid btn-sm" disabled={saving}>
            {saving ? 'Adding…' : 'Add rule'}
          </button>
          <button type="button" className="btn btn-outline btn-sm" disabled={sending || rules.length === 0} onClick={sendNow}>
            {sending ? 'Sending…' : 'Send now'}
          </button>
        </form>

        {error && <p className="form-error" style={{ marginTop: 8 }}>{error}</p>}
        {result && (
          <p style={{ marginTop: 8, fontSize: 'var(--text-sm)' }}>
            Sent {result.sent} · skipped {result.skipped} · failed {result.failed}
            {result.outcomes.some((o) => o.reason) && (
              <span style={{ color: 'var(--text-tertiary)' }}>
                {' '}({result.outcomes.filter((o) => o.reason).map((o) => o.reason).join('; ')})
              </span>
            )}
          </p>
        )}

        {rules.length > 0 && (
          <div style={{ marginTop: 12 }}>
            {rules.map((rule) => (
              <div key={rule.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-subtle, rgba(128,128,128,.15))' }}>
                <span style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-sm)' }}>{rule.to_email}</span>
                <span className="badge badge-neutral badge-sm">{rule.trigger_type.replace('_', ' ')}</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{rule.threshold_hours}h</span>
                <button type="button" className="btn btn-ghost btn-xs" onClick={() => toggle(rule)}>
                  {rule.enabled ? 'Disable' : 'Enable'}
                </button>
                <span className={`badge badge-sm ${rule.enabled ? 'badge-success' : 'badge-neutral'}`}>
                  {rule.enabled ? 'on' : 'off'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 'var(--space-5)' }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Send history</div>
        {log.length === 0 ? (
          <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>No emails sent yet.</p>
        ) : (
          log.map((entry) => (
            <div key={entry.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-subtle, rgba(128,128,128,.15))' }}>
              <StatusBadge kind="emailstatus" value={entry.status} />
              <span style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-sm)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={entry.error ?? undefined}>
                {entry.subject} → {entry.to_email}
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }} title={entry.sent_at}>
                {fmtTimestamp(entry.sent_at)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
