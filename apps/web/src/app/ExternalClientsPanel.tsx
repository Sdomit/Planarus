import { useEffect, useRef, useState } from 'react'
import {
  api,
  type ApiClientSummary,
  type Project,
  type Workspace,
} from '../api/client'
import { fmtTimestamp } from './format'
import './external-clients-panel.css'

const EXPIRY_OPTIONS = [30, 60, 90, 180, 365] as const
const DEFAULT_EXPIRY = 90

const EXPOSURE_WARNING =
  'The external API is disabled by default and should remain loopback-bound (127.0.0.1) unless you deliberately expose it. Keys grant read and/or pending-proposal access only — never approve or apply.'

interface ExternalClientsPanelProps { onClose: () => void }

// --- one-time raw-key modal — uses Forma modal classes ------------------

function RawKeyModal({ apiKey, onClose }: { apiKey: string; onClose: () => void }) {
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
    void navigator.clipboard?.writeText(apiKey).then(
      () => setCopied(true),
      () => setCopied(false),
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="new-api-key-title">
        <div className="modal-header">
          <span className="modal-title" id="new-api-key-title">API key created</span>
        </div>
        <div className="modal-body">
          <p style={{ color: 'var(--status-warning-fg)', fontSize: 'var(--text-sm)', marginTop: 0 }}>
            Copy and store this key now — it is shown <strong>only once</strong> and cannot be retrieved again.
          </p>
          <code style={{
            display: 'block', wordBreak: 'break-all',
            background: 'var(--bg-subtle)', border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)', padding: 'var(--space-3)',
            fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
            margin: 'var(--space-3) 0',
          }}>{apiKey}</code>
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

// --- create form -------------------------------------------------------

interface CreateFormProps {
  workspaceId: string
  projects: Project[]
  onCreated: (rawKey: string) => void
  onCancel: () => void
}

function CreateClientForm({ workspaceId, projects, onCreated, onCancel }: CreateFormProps) {
  const [label, setLabel] = useState('')
  const [projectIds, setProjectIds] = useState<string[]>([])
  const [canRead, setCanRead] = useState(true)
  const [canPropose, setCanPropose] = useState(false)
  const [expiry, setExpiry] = useState<number>(DEFAULT_EXPIRY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleProject = (id: string) =>
    setProjectIds(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id])

  const valid = label.trim() !== '' && projectIds.length > 0 && (canRead || canPropose)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setSaving(true); setError(null)
    api.apiClients
      .create({ label: label.trim(), workspace_id: workspaceId, project_ids: projectIds, can_read: canRead, can_propose: canPropose, expires_in_days: expiry })
      .then(res => onCreated(res.api_key))
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false))
  }

  return (
    <form className="ecp-form" onSubmit={submit}>
      <div className="form-field">
        <label className="form-label" htmlFor="ecp-client-label">Label</label>
        <input id="ecp-client-label" className="input" type="text" value={label}
          onChange={e => setLabel(e.target.value)} placeholder="e.g. ci-readonly" autoFocus />
      </div>

      <fieldset className="ecp-fieldset">
        <legend>Projects (at least one)</legend>
        {projects.length === 0
          ? <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 }}>No projects in this workspace.</p>
          : projects.map(p => (
            <label key={p.id} className="ecp-check-row">
              <input type="checkbox" checked={projectIds.includes(p.id)} onChange={() => toggleProject(p.id)} />
              <span>{p.title}</span>
            </label>
          ))}
      </fieldset>

      <fieldset className="ecp-fieldset">
        <legend>Permissions (at least one)</legend>
        <label className="ecp-check-row">
          <input type="checkbox" checked={canRead} onChange={e => setCanRead(e.target.checked)} />
          <span>can_read — bounded project reads</span>
        </label>
        <label className="ecp-check-row">
          <input type="checkbox" checked={canPropose} onChange={e => setCanPropose(e.target.checked)} />
          <span>can_propose — create pending proposals</span>
        </label>
      </fieldset>

      <div className="form-field">
        <label className="form-label" htmlFor="ecp-client-expiry">Expires in</label>
        <select id="ecp-client-expiry" className="input select" value={expiry} onChange={e => setExpiry(Number(e.target.value))}>
          {EXPIRY_OPTIONS.map(d => (
            <option key={d} value={d}>{d} days{d === DEFAULT_EXPIRY ? ' (default)' : ''}</option>
          ))}
        </select>
      </div>

      {error && <p className="ecp-error">{error}</p>}
      {!valid && <p className="ecp-hint">Provide a label, select at least one project, and grant at least one permission.</p>}

      <div className="ecp-form-actions">
        <button type="submit" disabled={!valid || saving} className="btn btn-solid btn-sm">
          {saving ? 'Creating…' : 'Create key'}
        </button>
        <button type="button" className="btn btn-outline btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

// --- root panel --------------------------------------------------------

export default function ExternalClientsPanel({ onClose: _onClose }: ExternalClientsPanelProps) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState('')
  const [projects, setProjects] = useState<Project[]>([])
  const [clients, setClients] = useState<ApiClientSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  // ponytail: raw key lives in memory only, cleared on modal close or unmount
  const [rawKey, setRawKey] = useState<string | null>(null)

  useEffect(() => {
    api.workspaces.list()
      .then(ws => { setWorkspaces(ws); if (ws[0]) setWorkspaceId(ws[0].id); else setLoading(false) })
      .catch((e: Error) => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => {
    if (!workspaceId) return
    setLoading(true); setError(null)
    Promise.all([api.projects.list(workspaceId), api.apiClients.list(workspaceId)])
      .then(([projs, cls]) => { setProjects(projs); setClients(cls) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [workspaceId])

  useEffect(() => () => setRawKey(null), [])

  const reloadClients = () => {
    if (!workspaceId) return
    api.apiClients.list(workspaceId).then(setClients).catch((e: Error) => setError(e.message))
  }

  const handleRevoke = (id: string) => {
    if (!window.confirm('Revoke this API key? This is permanent and cannot be undone.')) return
    api.apiClients.revoke(id).then(reloadClients).catch((e: Error) => setError(e.message))
  }

  const handleCreated = (key: string) => { setShowCreate(false); setRawKey(key); reloadClients() }

  return (
    <div className="ecp-panel">
      <p className="ecp-exposure" role="note">{EXPOSURE_WARNING}</p>

      <div className="ecp-toolbar">
        <label className="ecp-ws-label">
          Workspace
          <select className="input select input-sm" value={workspaceId}
            onChange={e => setWorkspaceId(e.target.value)} disabled={workspaces.length === 0}>
            {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <button type="button" className="btn btn-outline btn-sm"
          onClick={() => setShowCreate(v => !v)} disabled={!workspaceId}>
          {showCreate ? 'Cancel' : '+ New key'}
        </button>
      </div>

      {showCreate && workspaceId && (
        <CreateClientForm workspaceId={workspaceId} projects={projects}
          onCreated={handleCreated} onCancel={() => setShowCreate(false)} />
      )}

      {error && <p className="ecp-error">{error}</p>}

      {loading
        ? <p className="ecp-muted">Loading…</p>
        : clients.length === 0
          ? <p className="ecp-muted">No external API keys in this workspace.</p>
          : (
            <div className="ab-tablecard">
              <ul className="ecp-list">
                {clients.map(c => (
                  <li key={c.id} className={`ecp-item${c.revoked_at ? ' ecp-item-revoked' : ''}`}>
                    <div className="ecp-item-main">
                      <div className="ecp-item-heading">
                        <span className="ecp-item-label">{c.label}</span>
                        <span className="ecp-item-keyid">{c.key_id.slice(0, 10)}…</span>
                      </div>
                      <span className="ecp-item-details">
                        {c.project_ids.length} {c.project_ids.length === 1 ? 'project' : 'projects'}: {c.project_ids
                          .map(id => projects.find(project => project.id === id)?.title ?? id)
                          .join(', ')}
                        {' '}· Expires {fmtTimestamp(c.expires_at)}
                        {' '}· {c.last_used_at ? `Last used ${fmtTimestamp(c.last_used_at)}` : 'Never used'}
                      </span>
                    </div>
                    <div className="ecp-item-meta">
                      {c.can_read && <span className="ecp-perm">read</span>}
                      {c.can_propose && <span className="ecp-perm">propose</span>}
                      {!c.enabled && !c.revoked_at && <span className="ecp-revoked-label">disabled</span>}
                      {c.revoked_at
                        ? <span className="ecp-revoked-label">revoked</span>
                        : <button type="button" className="btn btn-destructive btn-xs" onClick={() => handleRevoke(c.id)}>Revoke</button>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

      {rawKey && <RawKeyModal apiKey={rawKey} onClose={() => setRawKey(null)} />}
    </div>
  )
}
