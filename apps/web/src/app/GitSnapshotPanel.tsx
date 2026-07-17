import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type GitBranch, type GitFetchResult, type GitSnapshot } from '../api/client'
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
      <Icon name="code" className="ic-16" />
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
      color: fetchMsg.tone === 'ok' ? 'var(--text-secondary)' : 'var(--warning, var(--text-secondary))',
    }}>
      {fetchMsg.text}
    </p>
  )

  if (failed || !snap || !snap.is_repo) {
    return (
      <div className="card" style={{ padding: 'var(--space-5)' }}>
        {header}
        {fetchNote}
        <p style={{ margin: 0, color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
          {(!failed && snap?.message) || 'No Git metadata available.'}
        </p>
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
    </div>
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
