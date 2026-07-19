import { useEffect, useRef, useState } from 'react'
import { api, type WebhookDelivery, type WebhookSubscription, type Workspace } from '../api/client'
import { fmtTimestamp } from './format'
import CopyButton from './CopyButton'

// P17.3b: Webhooks card for the Integrations tab. Create/list/delete signed
// outbound subscriptions, send a test event, and browse the delivery log with
// redeliver. Inert (404 → a config note) until AGENTBOARD_WEBHOOK_ENC_KEY is set.

type Fmt = 'json' | 'slack' | 'discord'
const FORMATS: Fmt[] = ['json', 'slack', 'discord']

const codeBox: React.CSSProperties = {
  display: 'block', wordBreak: 'break-all', background: 'var(--bg-subtle)',
  border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
  margin: 'var(--space-3) 0',
}

function SecretModal({ secret, onClose }: { secret: string; onClose: () => void }) {
  const doneRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    doneRef.current?.focus()
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])
  return (
    <div className="modal-overlay">
      <div className="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="wh-secret-title">
        <div className="modal-header">
          <span className="modal-title" id="wh-secret-title">Webhook signing secret</span>
        </div>
        <div className="modal-body">
          <p style={{ color: 'var(--status-warning-fg)', fontSize: 'var(--text-sm)', marginTop: 0 }}>
            Copy this now — it is shown <strong>only once</strong>. Your receiver verifies each
            delivery's <code>X-Approvo-Signature</code> header with it (HMAC-SHA256).
          </p>
          <code style={codeBox}>{secret}</code>
        </div>
        <div className="modal-footer">
          <CopyButton text={secret} />
          <button ref={doneRef} type="button" className="btn btn-solid btn-sm" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}

export default function WebhooksCard() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState('')
  const [subs, setSubs] = useState<WebhookSubscription[] | null>(null)
  const [inert, setInert] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [targetUrl, setTargetUrl] = useState('')
  const [format, setFormat] = useState<Fmt>('json')
  const [secret, setSecret] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([])

  useEffect(() => {
    api.workspaces.list()
      .then(ws => { setWorkspaces(ws); if (ws[0]) setWorkspaceId(ws[0].id) })
      .catch((e: Error) => setError(e.message))
  }, [])

  const reload = (wsId: string) => {
    api.webhooks.list(wsId)
      .then(rows => { setSubs(rows); setInert(false) })
      .catch((e: Error) => {
        if (String(e.message).startsWith('404')) { setInert(true); setSubs([]) }
        else setError(e.message)
      })
  }
  useEffect(() => { if (workspaceId) reload(workspaceId) }, [workspaceId])

  const create = () => {
    if (!targetUrl.trim() || !workspaceId) return
    setError(null)
    api.webhooks.create({ workspace_id: workspaceId, target_url: targetUrl.trim(), format })
      .then(res => { setSecret(res.secret); setTargetUrl(''); reload(workspaceId) })
      .catch((e: Error) => setError(e.message))
  }

  const remove = (id: string) => {
    if (!window.confirm('Delete this webhook? Deliveries stop immediately.')) return
    api.webhooks.remove(id).then(() => reload(workspaceId)).catch((e: Error) => setError(e.message))
  }

  const loadDeliveries = (id: string) =>
    api.webhooks.deliveries(id).then(setDeliveries).catch((e: Error) => setError(e.message))

  const toggle = (id: string) => {
    if (openId === id) { setOpenId(null); setDeliveries([]) }
    else { setOpenId(id); void loadDeliveries(id) }
  }

  const test = (id: string) =>
    api.webhooks.test(id).then(() => { if (openId === id) void loadDeliveries(id) }).catch((e: Error) => setError(e.message))

  const redeliver = (deliveryId: string, subId: string) =>
    api.webhooks.redeliver(deliveryId).then(() => loadDeliveries(subId)).catch((e: Error) => setError(e.message))

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>Webhooks</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Signed outbound POSTs when project events happen (<code>task.create</code>, <code>decision.create</code>,
        <code> doc.update</code>, …) — read &amp; notify only, never approve or apply. Drives n8n, Zapier, CI, Slack, Discord.
      </p>

      {inert ? (
        <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-sm)', margin: 0 }}>
          Inert until <code>AGENTBOARD_WEBHOOK_ENC_KEY</code> (a Fernet key) is set in the environment — the
          per-webhook signing secret is encrypted at rest with it. Install the <code>[webhooks]</code> extra.
        </p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 'var(--space-3)' }}>
            <div className="form-field">
              <label className="form-label" htmlFor="wh-ws">Workspace</label>
              <select id="wh-ws" className="input select input-sm" value={workspaceId} onChange={e => setWorkspaceId(e.target.value)} disabled={workspaces.length === 0}>
                {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="wh-fmt">Format</label>
              <select id="wh-fmt" className="input select input-sm" value={format} onChange={e => setFormat(e.target.value as Fmt)}>
                {FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div className="form-field" style={{ flex: 1, minWidth: 200 }}>
              <label className="form-label" htmlFor="wh-url">Target URL</label>
              <input id="wh-url" className="input input-sm" type="url" placeholder="https://your-endpoint/hook" value={targetUrl} onChange={e => setTargetUrl(e.target.value)} />
            </div>
            <button type="button" className="btn btn-solid btn-sm" onClick={create} disabled={!targetUrl.trim() || !workspaceId}>+ Add webhook</button>
          </div>

          {error && <p className="form-error" role="alert">{error}</p>}

          {subs === null ? (
            <p style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
          ) : subs.length === 0 ? (
            <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>No webhooks in this workspace yet.</p>
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 'var(--space-2)' }}>
              {subs.map(s => (
                <li key={s.id} style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                    <div style={{ minWidth: 0 }}>
                      <code style={{ fontSize: 'var(--text-xs)', wordBreak: 'break-all' }}>{s.target_url}</code>
                      <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-tertiary)' }}>{s.format}</span>
                      {!s.enabled && (
                        <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--status-warning-fg, var(--text-tertiary))' }}>
                          disabled after {s.failure_count} failures
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                      <button type="button" className="btn btn-outline btn-xs" onClick={() => test(s.id)}>Test</button>
                      <button type="button" className="btn btn-outline btn-xs" onClick={() => toggle(s.id)}>
                        {openId === s.id ? 'Hide log' : 'Deliveries'}
                      </button>
                      <button type="button" className="btn btn-destructive btn-xs" onClick={() => remove(s.id)}>Delete</button>
                    </div>
                  </div>
                  {openId === s.id && (
                    <div style={{ marginTop: 'var(--space-2)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--space-2)' }}>
                      {deliveries.length === 0 ? (
                        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', margin: 0 }}>No deliveries yet.</p>
                      ) : (
                        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 4 }}>
                          {deliveries.map(d => (
                            <li key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--text-xs)' }}>
                              <span>
                                <code>{d.event_kind}</code>{' · '}
                                <strong style={{ color: d.status === 'delivered' ? 'var(--status-success-fg, var(--text-primary))' : 'var(--status-warning-fg, var(--text-secondary))' }}>{d.status}</strong>
                                {d.status_code != null && ` ${d.status_code}`}{' · '}{fmtTimestamp(d.created_at)}
                              </span>
                              <button type="button" className="btn btn-ghost btn-xs" onClick={() => redeliver(d.id, s.id)}>Redeliver</button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {secret && <SecretModal secret={secret} onClose={() => setSecret(null)} />}
    </section>
  )
}
