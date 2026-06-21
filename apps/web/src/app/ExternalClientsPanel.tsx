import { useEffect, useState } from 'react'
import {
  api,
  type ApiClientSummary,
  type Project,
  type Workspace,
} from '../api/client'
import './external-clients-panel.css'

const EXPIRY_OPTIONS = [30, 60, 90, 180, 365] as const
const DEFAULT_EXPIRY = 90

const EXPOSURE_WARNING =
  'The external API is disabled by default and should remain loopback-bound (127.0.0.1) unless you deliberately expose it. Keys grant read and/or pending-proposal access only — never approve or apply.'

interface ExternalClientsPanelProps {
  onClose: () => void
}

// --- one-time raw-key modal --------------------------------------------------

function RawKeyModal({ apiKey, onClose }: { apiKey: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    void navigator.clipboard?.writeText(apiKey).then(
      () => setCopied(true),
      () => setCopied(false),
    )
  }

  return (
    <div className="ecp-modal" role="dialog" aria-label="New API key">
      <div className="ecp-modal-box">
        <h3>API key created</h3>
        <p className="ecp-warn">
          Copy and store this key now — it is shown <strong>only once</strong> and
          cannot be retrieved again.
        </p>
        <code className="ecp-key">{apiKey}</code>
        <div className="ecp-modal-actions">
          <button type="button" onClick={copy}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button type="button" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

// --- create form -------------------------------------------------------------

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
    setProjectIds((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]))

  const valid = label.trim() !== '' && projectIds.length > 0 && (canRead || canPropose)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setSaving(true)
    setError(null)
    api.apiClients
      .create({
        label: label.trim(),
        workspace_id: workspaceId,
        project_ids: projectIds,
        can_read: canRead,
        can_propose: canPropose,
        expires_in_days: expiry,
      })
      .then((res) => onCreated(res.api_key))
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false))
  }

  return (
    <form className="ecp-form" onSubmit={submit}>
      <label className="ecp-field">
        <span>Label</span>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. ci-readonly"
          autoFocus
        />
      </label>

      <fieldset className="ecp-fieldset">
        <legend>Projects (at least one)</legend>
        {projects.length === 0 ? (
          <p className="ecp-muted">No projects in this workspace.</p>
        ) : (
          projects.map((p) => (
            <label key={p.id} className="ecp-check-row">
              <input
                type="checkbox"
                checked={projectIds.includes(p.id)}
                onChange={() => toggleProject(p.id)}
              />
              <span>{p.title}</span>
            </label>
          ))
        )}
      </fieldset>

      <fieldset className="ecp-fieldset">
        <legend>Permissions (at least one)</legend>
        <label className="ecp-check-row">
          <input type="checkbox" checked={canRead} onChange={(e) => setCanRead(e.target.checked)} />
          <span>can_read — bounded project reads</span>
        </label>
        <label className="ecp-check-row">
          <input
            type="checkbox"
            checked={canPropose}
            onChange={(e) => setCanPropose(e.target.checked)}
          />
          <span>can_propose — create pending proposals</span>
        </label>
      </fieldset>

      <label className="ecp-field">
        <span>Expires in</span>
        <select value={expiry} onChange={(e) => setExpiry(Number(e.target.value))}>
          {EXPIRY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d} days{d === DEFAULT_EXPIRY ? ' (default)' : ''}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="ecp-error">{error}</p>}
      {!valid && (
        <p className="ecp-hint">
          Provide a label, select at least one project, and grant at least one permission.
        </p>
      )}

      <div className="ecp-form-actions">
        <button type="submit" disabled={!valid || saving}>
          {saving ? 'Creating…' : 'Create key'}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// --- root panel --------------------------------------------------------------

export default function ExternalClientsPanel({ onClose }: ExternalClientsPanelProps) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState('')
  const [projects, setProjects] = useState<Project[]>([])
  const [clients, setClients] = useState<ApiClientSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  // The raw key lives in memory only and is cleared when the modal closes or the
  // component unmounts. It is never written to storage, URLs, or logs.
  const [rawKey, setRawKey] = useState<string | null>(null)

  useEffect(() => {
    api.workspaces
      .list()
      .then((ws) => {
        setWorkspaces(ws)
        if (ws[0]) setWorkspaceId(ws[0].id)
        else setLoading(false)
      })
      .catch((e: Error) => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!workspaceId) return
    setLoading(true)
    setError(null)
    Promise.all([api.projects.list(workspaceId), api.apiClients.list(workspaceId)])
      .then(([projs, cls]) => {
        setProjects(projs)
        setClients(cls)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [workspaceId])

  // Defence-in-depth: clear the one-time key from memory on unmount.
  useEffect(() => () => setRawKey(null), [])

  const reloadClients = () => {
    if (!workspaceId) return
    api.apiClients.list(workspaceId).then(setClients).catch((e: Error) => setError(e.message))
  }

  const handleRevoke = (id: string) => {
    if (!window.confirm('Revoke this API key? This is permanent and cannot be undone.')) return
    api.apiClients
      .revoke(id)
      .then(reloadClients)
      .catch((e: Error) => setError(e.message))
  }

  const handleCreated = (key: string) => {
    setShowCreate(false)
    setRawKey(key)
    reloadClients()
  }

  return (
    <div className="ecp-panel">
      <div className="ecp-panel-header">
        <span className="ecp-panel-title">External API Clients</span>
        <button className="ecp-close" onClick={onClose} title="Close">
          ✕
        </button>
      </div>

      <p className="ecp-exposure" role="note">
        {EXPOSURE_WARNING}
      </p>

      <div className="ecp-toolbar">
        <label className="ecp-ws-select">
          Workspace:
          <select
            value={workspaceId}
            onChange={(e) => setWorkspaceId(e.target.value)}
            disabled={workspaces.length === 0}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="ecp-new"
          onClick={() => setShowCreate((v) => !v)}
          disabled={!workspaceId}
        >
          {showCreate ? 'Cancel' : '+ New key'}
        </button>
      </div>

      {showCreate && workspaceId && (
        <CreateClientForm
          workspaceId={workspaceId}
          projects={projects}
          onCreated={handleCreated}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {error && <p className="ecp-error">{error}</p>}
      {loading ? (
        <p className="ecp-muted">Loading…</p>
      ) : clients.length === 0 ? (
        <p className="ecp-muted">No external API keys in this workspace.</p>
      ) : (
        <ul className="ecp-list">
          {clients.map((c) => (
            <li key={c.id} className={`ecp-item${c.revoked_at ? ' ecp-item-revoked' : ''}`}>
              <div className="ecp-item-main">
                <span className="ecp-item-label">{c.label}</span>
                <span className="ecp-item-keyid">{c.key_id.slice(0, 10)}…</span>
              </div>
              <div className="ecp-item-meta">
                {c.can_read && <span className="ecp-perm">read</span>}
                {c.can_propose && <span className="ecp-perm">propose</span>}
                <span className="ecp-projects">{c.project_ids.length} project(s)</span>
                {c.revoked_at ? (
                  <span className="ecp-revoked">revoked</span>
                ) : (
                  <button type="button" className="ecp-revoke" onClick={() => handleRevoke(c.id)}>
                    Revoke
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {rawKey && <RawKeyModal apiKey={rawKey} onClose={() => setRawKey(null)} />}
    </div>
  )
}
