import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type GitBranch, type GitFetchResult, type GitPrSummary, type GitSnapshot } from '../api/client'
import { Icon } from './Icon'
import { agoLabel, dayLabel } from './date'

// Phase 12a repo cockpit — SHOW, DON'T DO. Read-only view of local Git state;
// "live" = refetch on view + window focus (debounced to match the backend's
// short TTL cache), never a background poller. The one exception is the Phase
// 12b "Fetch now" button — an explicit, human-clicked, gated outbound action.
const MIN_REFRESH_MS = 3000
const BRANCH_ROWS = 8

export default function GitSnapshotPanel({ projectId }: { projectId: string }) {
  const [snap, setSnap] = useState<GitSnapshot | null>(null)
  const [failed, setFailed] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState<{ tone: 'ok' | 'warn'; text: string } | null>(null)
  const lastRefresh = useRef(0)

  const load = useCallback(async (force: boolean) => {
    if (!force && Date.now() - lastRefresh.current < MIN_REFRESH_MS) return
    lastRefresh.current = Date.now()
    try {
      setSnap(await api.git.snapshot(projectId))
      setFailed(false)
    } catch {
      setFailed(true)
    }
  }, [projectId])

  useEffect(() => { void load(true) }, [load])
  useEffect(() => {
    const onFocus = () => void load(false)
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [load])

  const onFetch = useCallback(async () => {
    setFetching(true)
    setFetchMsg(null)
    try {
      const res: GitFetchResult = await api.git.fetchNow(projectId)
      if (res.snapshot) setSnap(res.snapshot)  // refresh stamp + refs in one shot
      if (res.status === 'ok') {
        setFetchMsg({ tone: 'ok', text: `Fetched from ${res.remote}.` })
      } else {
        setFetchMsg({ tone: 'warn', text: res.message ?? 'Fetch did not complete.' })
      }
    } catch (e) {
      // Disabled (409) and any other error surface as a message; the offline
      // cockpit keeps working regardless.
      const msg = e instanceof Error ? e.message : 'Fetch failed.'
      setFetchMsg({ tone: 'warn', text: msg })
    } finally {
      setFetching(false)
    }
  }, [projectId])

  const fetchButton = snap?.is_repo && (
    <button
      type="button"
      className="btn btn-outline btn-sm"
      onClick={onFetch}
      disabled={fetching}
      title="Fetch remote-tracking refs now (the only outbound Git action)"
    >
      {fetching ? <span className="spinner spinner-sm" /> : <Icon name="external" className="ic-14" />}
      {fetching ? ' Fetching…' : ' Fetch now'}
    </button>
  )

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--space-3)', flexWrap: 'wrap' }}>
      <Icon name="code" />
      <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>Repository</span>
      <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>read-only</span>
      {snap?.is_repo && (
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-tertiary)' }}>
          {snap.last_fetched_at
            ? `remote state as of last fetch, ${agoLabel(snap.last_fetched_at)}`
            : 'no fetch recorded — remote state may be stale'}
        </span>
      )}
      {fetchButton}
    </div>
  )

  const fetchNote = fetchMsg && (
    <p style={{
      margin: '0 0 var(--space-3)', fontSize: 'var(--text-xs)',
      color: fetchMsg.tone === 'ok' ? 'var(--text-secondary)' : 'var(--status-warning-fg)',
    }}>
      {fetchMsg.text}
    </p>
  )

  if (failed || !snap || !snap.is_repo) {
    return (
      <div className="card" style={{ padding: 'var(--space-5)' }}>
        {header}
        {fetchNote}
        <p style={{ margin: '0 0 var(--space-3)', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
          {(!failed && snap?.message) || 'No Git metadata available.'}
        </p>
        <FolderField projectId={projectId} current={snap?.repo_path ?? null} onSaved={() => void load(true)} />
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: 'var(--space-5)' }}>
      {header}
      {fetchNote}
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 'var(--space-2) var(--space-4)', margin: 0 }}>
        <Row k="Branch">
          {snap.detached
            ? <span style={{ color: 'var(--text-secondary)' }}>detached HEAD</span>
            : <code style={{ fontSize: 'var(--text-sm)' }}>{snap.current_branch ?? '—'}</code>}
          {snap.working_tree?.ahead != null && (
            <span style={{ marginLeft: 8, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              <UpDown ahead={snap.working_tree.ahead} behind={snap.working_tree.behind} /> vs upstream
            </span>
          )}
        </Row>
        <Row k="Working tree"><WorkingTreeBadge snap={snap} /></Row>
        <Row k="Last commit">
          {snap.last_commit_sha
            ? <span><code style={{ fontSize: 'var(--text-sm)' }}>{snap.last_commit_sha}</code>{' '}{snap.last_commit_subject}</span>
            : <span style={{ color: 'var(--text-tertiary)' }}>no commits yet</span>}
        </Row>
        <Row k="Remote">
          {snap.remote_url
            ? <code style={{ fontSize: 'var(--text-sm)', overflowWrap: 'anywhere' }}>{snap.remote_url}</code>
            : <span style={{ color: 'var(--text-tertiary)' }}>none</span>}
        </Row>
        <Row k="Folder">
          <FolderField projectId={projectId} current={snap.repo_path} onSaved={() => void load(true)} />
        </Row>
        {snap.default_branch && (
          <Row k="Needs merge">
            {snap.needs_merge.length === 0 ? (
              <span className="sbadge sbadge--success"><span className="sdot" />everything merged into {snap.default_branch}</span>
            ) : (
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {snap.needs_merge.map((name) => (
                  <span key={name} className="sbadge sbadge--warning"><span className="sdot" /><code style={{ fontSize: 'var(--text-xs)' }}>{name}</code></span>
                ))}
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>into {snap.default_branch}</span>
              </span>
            )}
          </Row>
        )}
      </dl>
      <BranchTable snap={snap} />
      <PrSection projectId={projectId} />
    </div>
  )
}

// Phase 12c: read-only open-PR list via the local gh CLI. Click-to-load only —
// Planarus never auto-polls an outbound surface; the backend adds a 60s TTL.
function PrSection({ projectId }: { projectId: string }) {
  const [summary, setSummary] = useState<GitPrSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [linked, setLinked] = useState<Record<number, 'saving' | 'done' | 'failed'>>({})

  const loadPrs = useCallback(async () => {
    setLoading(true)
    try {
      setSummary(await api.git.prs(projectId))
    } catch (e) {
      setSummary({
        project_id: projectId, status: 'failed', authenticated: false,
        message: e instanceof Error ? e.message : 'Could not load pull requests.',
        prs: [], checked_at: '',
      })
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const attach = useCallback(async (n: number, url: string, title: string) => {
    setLinked((m) => ({ ...m, [n]: 'saving' }))
    try {
      await api.links.create(projectId, {
        entity_type: 'project', entity_id: projectId, url, title: `PR #${n} — ${title}`,
      })
      setLinked((m) => ({ ...m, [n]: 'done' }))
    } catch {
      setLinked((m) => ({ ...m, [n]: 'failed' }))
    }
  }, [projectId])

  const td = { fontSize: 'var(--text-sm)', color: 'var(--text-primary)', padding: '4px 12px 4px 0' }
  return (
    <div style={{ marginTop: 'var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          Pull requests
        </span>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={loadPrs}
          disabled={loading}
          title="Read open PRs via your local GitHub CLI (gh) — read-only, nothing stored"
        >
          {loading ? <span className="spinner spinner-sm" /> : <Icon name="external" className="ic-14" />}
          {loading ? ' Loading…' : summary ? ' Refresh PRs' : ' Load PRs'}
        </button>
      </div>
      {summary && summary.status !== 'ok' && (
        <p style={{ margin: 'var(--space-2) 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          {summary.message ?? 'Pull requests unavailable.'}
        </p>
      )}
      {summary?.status === 'ok' && summary.prs.length === 0 && (
        <p style={{ margin: 'var(--space-2) 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          No open pull requests.
        </p>
      )}
      {summary?.status === 'ok' && summary.prs.length > 0 && (
        <div style={{ marginTop: 'var(--space-2)', overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <tbody>
              {summary.prs.map((pr) => (
                <tr key={pr.number}>
                  <td style={{ ...td, whiteSpace: 'nowrap' }}>
                    {pr.url
                      ? <a href={pr.url} target="_blank" rel="noreferrer">#{pr.number}</a>
                      : <span>#{pr.number}</span>}
                  </td>
                  <td style={td}>
                    {pr.title}
                    {pr.is_draft && (
                      <span className="sbadge" style={{ marginLeft: 6 }}>draft</span>
                    )}
                  </td>
                  <td style={{ ...td, whiteSpace: 'nowrap' }}>
                    <code style={{ fontSize: 'var(--text-xs)' }}>{pr.head ?? '?'}</code>
                    <span style={{ color: 'var(--text-tertiary)' }}> → </span>
                    <code style={{ fontSize: 'var(--text-xs)' }}>{pr.base ?? '?'}</code>
                  </td>
                  <td style={{ ...td, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                    {pr.author ?? '—'}{pr.updated_at ? ` · ${agoLabel(pr.updated_at)}` : ''}
                  </td>
                  <td style={{ ...td, whiteSpace: 'nowrap' }}>
                    {pr.url && (
                      linked[pr.number] === 'done'
                        ? <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>linked ✓</span>
                        : (
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            disabled={linked[pr.number] === 'saving'}
                            onClick={() => void attach(pr.number, pr.url as string, pr.title)}
                            title="Save this PR as a project link"
                          >
                            {linked[pr.number] === 'failed' ? 'Link failed — retry' : 'Add link'}
                          </button>
                        )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// Point the project at a repo folder so the live status can be read. A native
// folder picker can't hand back an absolute path (browser security), so this is
// a plain text field — the server validates it must be absolute and existing.
function FolderField({ projectId, current, onSaved }: {
  projectId: string; current: string | null; onSaved: () => void
}) {
  const [editing, setEditing] = useState(current == null)
  const [value, setValue] = useState(current ?? '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      await api.projects.update(projectId, { folder_path: value.trim() || null })
      setEditing(false)
      onSaved()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not save the folder path.')
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <code style={{ fontSize: 'var(--text-sm)', overflowWrap: 'anywhere' }}>{current}</code>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => { setValue(current ?? ''); setEditing(true) }}>
          Change
        </button>
      </span>
    )
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <input
        className="input input-sm"
        style={{ minWidth: 260, fontFamily: 'var(--font-mono, monospace)' }}
        placeholder="Absolute path, e.g. C:\Users\you\repo"
        value={value}
        spellCheck={false}
        autoFocus
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') void save() }}
      />
      <button type="button" className="btn btn-solid btn-sm" onClick={() => void save()} disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </button>
      {current != null && (
        <button type="button" className="btn btn-outline btn-sm" onClick={() => { setEditing(false); setErr(null) }} disabled={saving}>
          Cancel
        </button>
      )}
      {err && <span style={{ width: '100%', fontSize: 'var(--text-xs)', color: 'var(--status-danger-fg)' }}>{err}</span>}
    </span>
  )
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div style={{ display: 'contents' }}>
      <dt style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', alignSelf: 'center' }}>{k}</dt>
      <dd style={{ margin: 0, minWidth: 0, overflowWrap: 'anywhere', color: 'var(--text-primary)' }}>{children}</dd>
    </div>
  )
}

function WorkingTreeBadge({ snap }: { snap: GitSnapshot }) {
  const tree = snap.working_tree
  if (!tree) return <span style={{ color: 'var(--text-tertiary)' }}>unknown</span>
  const parts = [
    tree.staged && `${tree.staged} staged`,
    tree.unstaged && `${tree.unstaged} unstaged`,
    tree.untracked && `${tree.untracked} untracked`,
    tree.conflicted && `${tree.conflicted} conflicted`,
  ].filter(Boolean)
  const dirty = parts.length > 0
  return (
    <span className={`sbadge ${dirty ? 'sbadge--warning' : 'sbadge--success'}`}>
      <span className="sdot" />{dirty ? parts.join(' · ') : 'clean'}
    </span>
  )
}

function UpDown({ ahead, behind }: { ahead: number | null; behind: number | null }) {
  if (ahead == null && behind == null) return <span>—</span>
  return <span>↑{ahead ?? '?'} ↓{behind ?? '?'}</span>
}

function BranchTable({ snap }: { snap: GitSnapshot }) {
  const shown = snap.branches.slice(0, BRANCH_ROWS)
  const hidden = snap.branches_total - shown.length
  if (shown.length === 0) return null
  const th = { textAlign: 'left' as const, fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 500, padding: '4px 12px 4px 0' }
  const td = { fontSize: 'var(--text-sm)', color: 'var(--text-primary)', padding: '4px 12px 4px 0', whiteSpace: 'nowrap' as const }
  return (
    <div style={{ marginTop: 'var(--space-4)', overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={th}>Branch ({snap.branches_total})</th>
            <th style={th}>Upstream</th>
            <th style={th}>vs {snap.default_branch ?? 'default'}</th>
            <th style={th}>Last commit</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((branch) => <BranchRow key={branch.name} branch={branch} tdStyle={td} />)}
        </tbody>
      </table>
      {hidden > 0 && (
        <p style={{ margin: 'var(--space-2) 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          +{hidden} more by recency
        </p>
      )}
    </div>
  )
}

function BranchRow({ branch, tdStyle }: { branch: GitBranch; tdStyle: React.CSSProperties }) {
  return (
    <tr>
      <td style={tdStyle}>
        <code style={{ fontSize: 'var(--text-sm)' }}>{branch.name}</code>
        {branch.is_current && <span title="checked out" style={{ marginLeft: 6, color: 'var(--accent, currentColor)' }}>●</span>}
      </td>
      <td style={tdStyle}>
        {branch.upstream == null
          ? <span style={{ color: 'var(--text-tertiary)' }}>none</span>
          : branch.gone
            ? <span style={{ color: 'var(--text-tertiary)' }}>gone</span>
            : <UpDown ahead={branch.ahead} behind={branch.behind} />}
      </td>
      <td style={tdStyle}>
        {branch.ahead_of_default == null && branch.behind_default == null
          ? <span style={{ color: 'var(--text-tertiary)' }}>—</span>
          : <UpDown ahead={branch.ahead_of_default} behind={branch.behind_default} />}
      </td>
      <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>
        {branch.committed_at ? dayLabel(branch.committed_at) : '—'}
      </td>
    </tr>
  )
}
