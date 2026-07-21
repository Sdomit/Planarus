import { useEffect, useState } from 'react'
import { api, type AppSettingsUpdate, type BackupFile, type BackupResult } from '../api/client'

// P18.2/18.4 (D42/D44): the UI over Phase 18's verified backups. The switches
// belong to SettingsPanel's shared state and land with its global Save; this
// card owns only the listing and "Back up now", which fires immediately —
// taking a backup is a verb, not a preference.
//
// Hence `savedEnabled`: the server refuses a backup while the *stored* switch is
// off, so gating the button on the live (possibly unsaved) checkbox would offer
// an action guaranteed to 409.

type Props = {
  enabled: boolean
  savedEnabled: boolean
  retention: number
  offsite: boolean
  supported: boolean
  offsiteSupported: boolean
  dirConfigured: boolean
  onChange: (next: AppSettingsUpdate) => void
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function humanTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export default function BackupsCard({
  enabled,
  savedEnabled,
  retention,
  offsite,
  supported,
  offsiteSupported,
  dirConfigured,
  onChange,
}: Props) {
  const [backups, setBackups] = useState<BackupFile[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [made, setMade] = useState<BackupResult | null>(null)

  const refresh = () => {
    api.backups
      .list()
      .then(setBackups)
      .catch((e: Error) => setError(e.message))
  }

  useEffect(() => {
    refresh()
  }, [])

  const backUpNow = () => {
    setBusy(true)
    setError(null)
    setMade(null)
    api.backups
      .create()
      .then(r => {
        setMade(r)
        refresh()
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const unsaved = enabled !== savedEnabled

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>Backups</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        One consistent snapshot of the whole database, integrity-checked before it counts. Different
        from Export above: export moves <em>one project</em> and is lossy by design; a backup is the
        faithful copy you restore from. Restoring is a command, never a button —{' '}
        <code>python -m app.jobs restore</code>.
      </p>

      {!supported && (
        <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
          This database is not SQLite, so file-snapshot backups are unavailable. Use{' '}
          <code>pg_dump</code> or your platform&apos;s managed snapshots with point-in-time recovery.
        </p>
      )}

      <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={enabled}
          disabled={!supported}
          onChange={e => onChange({ backup_enabled: e.target.checked })}
        />
        <span>Enable backups</span>
      </label>

      <div className="form-field" style={{ marginTop: 'var(--space-3)' }}>
        <label className="form-label" htmlFor="set-backup-retention">Keep last</label>
        <input
          id="set-backup-retention"
          className="input input-sm"
          type="number"
          min={1}
          max={365}
          style={{ maxWidth: 120 }}
          value={retention}
          disabled={!supported}
          onChange={e => {
            const n = parseInt(e.target.value, 10)
            if (!Number.isNaN(n)) onChange({ backup_retention: n })
          }}
        />
        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
          Older backups are pruned; only files Planarus generated are ever deleted. Destination is{' '}
          <code>PLANARUS_BACKUP_DIR</code> (configured: <strong>{dirConfigured ? 'Yes' : 'No'}</strong>).
        </p>
      </div>

      <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 'var(--space-3)' }}>
        <input
          type="checkbox"
          checked={offsite}
          disabled={!supported || !offsiteSupported}
          onChange={e => onChange({ backup_offsite: e.target.checked })}
        />
        <span>Also copy each backup off-site</span>
      </label>
      <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
        {offsiteSupported ? (
          <>A copy goes to your configured object storage after each verified snapshot.</>
        ) : (
          <>
            Needs an object-storage backend (<code>PLANARUS_STORAGE_BACKEND=s3</code>). On the
            default local backend this would copy the file beside the original — point{' '}
            <code>PLANARUS_BACKUP_DIR</code> at a synced folder instead.
          </>
        )}{' '}
        A backup on the same disk survives a bad migration, not a dead disk.
      </p>

      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', marginTop: 'var(--space-3)', flexWrap: 'wrap' }}>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={backUpNow}
          disabled={busy || !supported || !savedEnabled}
        >
          {busy ? 'Backing up…' : 'Back up now'}
        </button>
        {made && (
          <span style={{ color: 'var(--status-success-fg, var(--text-secondary))', fontSize: 'var(--text-sm)' }}>
            {made.backup.name}
            {made.pruned > 0 ? ` · pruned ${made.pruned}` : ''}
            {made.offsite ? ' · copied off-site' : ''} ✓
          </span>
        )}
      </div>

      {made?.offsite_error && (
        <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
          Backed up locally, but the off-site copy did not happen: {made.offsite_error}
        </p>
      )}

      {unsaved && (
        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: '6px 0 0' }}>
          Save your change before taking a backup — the server reads the stored setting.
        </p>
      )}

      {backups.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 'var(--space-3) 0 0', display: 'grid', gap: 4 }}>
          {backups.map(b => (
            <li
              key={b.name}
              style={{ display: 'flex', gap: 8, justifyContent: 'space-between', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}
            >
              <code style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{b.name}</code>
              <span style={{ whiteSpace: 'nowrap', color: 'var(--text-tertiary)' }}>
                {humanSize(b.size_bytes)} · {humanTime(b.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="form-error" role="alert" style={{ marginTop: 'var(--space-2)' }}>{error}</p>}
    </section>
  )
}
