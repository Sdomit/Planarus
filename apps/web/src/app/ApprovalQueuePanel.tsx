import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  type ApprovalAuditEntry,
  type ApprovalDetail,
  type ApprovalSummary,
} from '../api/client'
import { fmtTimestamp } from './format'
import { StatusBadge } from './StatusBadge'
import './approval-queue-panel.css'

const OPEN_STATES = ['pending', 'approved', 'applying']
// #154 review: the actionable rows are fetched by status, not sliced out of a
// capped page. Ordered by creation time, an old still-pending proposal falls off
// a 200-row page once enough decided history piles up in front of it — and the
// panel is the only place it can be approved, rejected or applied. History is
// the half it is safe to clip.
const OPEN_FILTER = OPEN_STATES.join(',')

// #96: the list used to load once on mount, so sitting on the Approvals view
// while an agent worked showed a queue that never grew. Same interval as
// NotificationsBell, which was already polling while this panel was not.
const POLL_MS = 60_000

interface ApprovalQueuePanelProps { projectId: string; onClose: () => void }

function targetLabel(a: ApprovalSummary): string {
  if (a.target_title) return a.target_title
  if (a.target_entity_id) return `${a.target_entity_type}:${a.target_entity_id.slice(0, 14)}`
  return `new ${a.target_entity_type ?? 'entity'}`
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return '∅'
  if (typeof v === 'string') return v === '' ? '(empty)' : v
  return JSON.stringify(v)
}

export default function ApprovalQueuePanel({ projectId }: ApprovalQueuePanelProps) {
  const [openItems, setOpenItems] = useState<ApprovalSummary[]>([])
  const [historyItems, setHistoryItems] = useState<ApprovalSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Total row count when the server returned only part of it; null when whole.
  const [clipped, setClipped] = useState<number | null>(null)

  const [selected, setSelected] = useState<ApprovalDetail | null>(null)
  const [audit, setAudit] = useState<ApprovalAuditEntry[]>([])
  const [detailError, setDetailError] = useState<string | null>(null)

  const [rejectReason, setRejectReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const [checked, setChecked] = useState<string[]>([])
  const [bulkErrors, setBulkErrors] = useState<string[]>([])
  // A poll that lands mid-decision would repaint the list from a snapshot the
  // server took before the write. Skip that tick instead of racing it.
  const actingRef = useRef(false)

  const loadList = useCallback((silent = false) => {
    if (!silent) setLoading(true)
    setLoadError(null)
    return Promise.all([
      api.approvals.listPaged(projectId, OPEN_FILTER),
      api.approvals.listPaged(projectId),
    ])
      .then(([openPage, recentPage]) => {
        setOpenItems(openPage.items)
        // The second call is unfiltered, so drop the actionable rows it repeats.
        setHistoryItems(recentPage.items.filter(a => !OPEN_STATES.includes(a.status)))
        // #103: the server caps the history list. Say so rather than quietly
        // showing a partial history that looks complete.
        setClipped(recentPage.hasMore ? recentPage.total : null)
        // Drop selections whose row is no longer pending — decided elsewhere,
        // or by the bulk run that just finished.
        const stillOpen = new Set(
          openPage.items.filter(a => a.status === 'pending').map(a => a.id),
        )
        setChecked(prev => prev.filter(id => stillOpen.has(id)))
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => { if (!silent) setLoading(false) })
  }, [projectId])

  useEffect(() => { loadList() }, [loadList])

  useEffect(() => {
    const timer = setInterval(() => { if (!actingRef.current) loadList(true) }, POLL_MS)
    return () => clearInterval(timer)
  }, [loadList])

  const openDetail = useCallback((id: string) => {
    setDetailError(null); setActionError(null); setRejectReason('')
    return Promise.all([api.approvals.get(id), api.approvals.audit(id)])
      .then(([d, a]) => { setSelected(d); setAudit(a) })
      .catch((e: Error) => setDetailError(e.message))
  }, [])

  const runAction = useCallback((id: string, fn: () => Promise<ApprovalSummary>) => {
    setBusy(true); setActionError(null); actingRef.current = true
    fn()
      .then(updated => {
        setSelected(prev => prev ? { ...prev, ...updated } : prev)
        const patch = (prev: ApprovalSummary[]) =>
          prev.map(it => it.id === updated.id ? { ...it, ...updated } : it)
        setOpenItems(patch)
        setHistoryItems(patch)
        api.approvals.audit(id).then(setAudit).catch(() => undefined)
      })
      .catch((e: Error) => setActionError(e.message))
      .finally(() => { setBusy(false); actingRef.current = false })
  }, [])

  // #96: approve and apply were two round-trips and two clicks on every single
  // proposal. This is still two requests — the server deliberately has no
  // combined route, so that apply keeps re-running its stale-state checks
  // against the freshly approved row — but one decision by the human.
  // ponytail: if apply fails after approve succeeded the row stays `approved`,
  // which is exactly the state the standalone Apply button already handles.
  const approveAndApply = useCallback(
    (id: string) => api.approvals.approve(id).then(() => api.approvals.apply(id)),
    [],
  )

  const pending = openItems
  const history = historyItems
  const selectable = pending.filter(a => a.status === 'pending')
  const allChecked = selectable.length > 0 && checked.length === selectable.length

  const toggleRow = (id: string) =>
    setChecked(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const toggleAll = () =>
    setChecked(allChecked ? [] : selectable.map(a => a.id))

  // Sequential, not Promise.all: the API is a single process (#120) and each
  // apply mutates canonical state, so a failure should stop nothing but its own
  // row and the ordering should stay the one the human saw.
  const runBulk = useCallback(async () => {
    const ids = [...checked]
    if (ids.length === 0) return
    setBusy(true); setBulkErrors([]); setActionError(null); actingRef.current = true
    const failures: string[] = []
    for (const id of ids) {
      try {
        await approveAndApply(id)
      } catch (e) {
        failures.push(`${id.slice(0, 14)}: ${(e as Error).message}`)
      }
    }
    setBulkErrors(failures)
    actingRef.current = false
    await loadList(true)
    if (selected && ids.includes(selected.id)) await openDetail(selected.id)
    setBusy(false)
  }, [checked, approveAndApply, loadList, openDetail, selected])

  const renderRow = (a: ApprovalSummary, withCheckbox = false) => {
    const row = (
      <button
        key={a.id} type="button"
        className={`aqp-row${selected?.id === a.id ? ' aqp-row-selected' : ''}`}
        onClick={() => openDetail(a.id)}
      >
        <span className={`aqp-origin${a.origin === 'api' ? ' api' : ''}`}>{a.origin}</span>
        <span className="aqp-row-action">{a.action_type}</span>
        <span className="aqp-row-target" title={a.target_entity_id ?? undefined}>{targetLabel(a)}</span>
        <StatusBadge kind="severity" value={a.risk_level} />
        <StatusBadge kind="approval" value={a.status} />
      </button>
    )
    if (!withCheckbox || a.status !== 'pending') return row
    return (
      <div className="aqp-row-wrap" key={a.id}>
        <input
          type="checkbox" className="aqp-check"
          aria-label={`Select ${a.action_type} for bulk approve and apply`}
          checked={checked.includes(a.id)} disabled={busy}
          onChange={() => toggleRow(a.id)}
        />
        {row}
      </div>
    )
  }

  return (
    <div className="aqp-panel">
      <p className="aqp-notice" role="note">
        Proposals are reference-only until you approve and apply them. Planarus never applies a change on its own.
      </p>

      <div className="aqp-body">
        {/* Left: queue list */}
        <div className="aqp-list">
          {loading && <p className="aqp-state">Loading approvals…</p>}
          {loadError && <p className="aqp-state aqp-error">{loadError}</p>}
          {!loading && !loadError && (
            <>
              <section>
                <h3 className="aqp-section-title">Pending ({pending.length})</h3>
                {selectable.length > 0 && (
                  <div className="aqp-bulk">
                    <label className="aqp-bulk-all">
                      <input
                        type="checkbox" checked={allChecked} disabled={busy}
                        onChange={toggleAll} aria-label="Select all pending proposals"
                      />
                      Select all
                    </label>
                    <button
                      type="button" className="btn btn-solid btn-sm"
                      disabled={busy || checked.length === 0} onClick={runBulk}
                    >
                      Approve &amp; apply ({checked.length})
                    </button>
                  </div>
                )}
                {pending.length === 0
                  ? <p className="aqp-empty">No pending proposals.</p>
                  : pending.map(a => renderRow(a, true))}
                {bulkErrors.length > 0 && (
                  <ul className="aqp-state aqp-error aqp-bulk-errors">
                    {bulkErrors.map(msg => <li key={msg}>{msg}</li>)}
                  </ul>
                )}
              </section>
              <section>
                <h3 className="aqp-section-title">History ({history.length})</h3>
                {history.length === 0
                  ? <p className="aqp-empty">No decided proposals yet.</p>
                  : history.map(a => renderRow(a))}
              </section>
              {clipped !== null && (
                <p className="aqp-state">
                  Showing every open proposal, and the {historyItems.length} most
                  recent of {clipped} total. Older decided proposals are not listed.
                </p>
              )}
            </>
          )}
        </div>

        {/* Right: detail pane */}
        <div className="aqp-detail">
          {detailError && <p className="aqp-state aqp-error">{detailError}</p>}
          {!selected ? (
            <p className="aqp-empty">Select a proposal to review it.</p>
          ) : (
            <>
              <div className="aqp-detail-head">
                <span className="aqp-detail-action">{selected.action_type}</span>
                <StatusBadge kind="approval" value={selected.status} />
              </div>

              <dl className="aqp-meta">
                <div><dt>Origin</dt><dd>{selected.origin}</dd></div>
                <div><dt>Project</dt><dd title={selected.project_id}>{selected.project_id.slice(0, 18)}…</dd></div>
                <div><dt>Target</dt><dd title={selected.target_entity_id ?? undefined}>{targetLabel(selected)}</dd></div>
                <div><dt>Risk</dt><dd><StatusBadge kind="severity" value={selected.risk_level} /></dd></div>
                {selected.decided_by && (
                  <div><dt>Decided by</dt><dd>{selected.decided_by_display ?? selected.decided_by}</dd></div>
                )}
                <div><dt>Expires</dt><dd title={selected.expires_at}>{fmtTimestamp(selected.expires_at)}</dd></div>
                <div><dt>Checksum</dt><dd className="aqp-checksum">{selected.patch_checksum.slice(0, 16)}</dd></div>
              </dl>

              {selected.is_expired && (
                <div className="alert alert-warning" role="alert">
                  <span className="alert-body">⚠ This proposal has expired and can no longer be applied.</span>
                </div>
              )}
              {selected.stale_reason && (
                <div className="alert alert-warning" role="alert">
                  <span className="alert-body">⚠ Stale: {selected.stale_reason}. Applying will be blocked; a new proposal is required.</span>
                </div>
              )}

              <p className="aqp-secret-note">
                🔒 Secrets are blocked at proposal time (best-effort); patch content is never logged or audited.
              </p>

              <h4 className="aqp-diff-title">Proposed change (before → after)</h4>
              {selected.diff.length === 0
                ? <p className="aqp-empty">No fields.</p>
                : (
                  <ul className="aqp-diff">
                    {selected.diff.map(d => (
                      <li key={d.field}>
                        <span className="aqp-diff-field">{d.field}</span>
                        <span className="aqp-diff-before">{renderValue(d.before)}</span>
                        <span className="aqp-diff-arrow">→</span>
                        <span className="aqp-diff-after">{renderValue(d.after)}</span>
                      </li>
                    ))}
                  </ul>
                )}

              <p className="aqp-mandatory">
                Approving allows Planarus to apply only this exact proposal once.
              </p>

              {/* #96: above the buttons, not below — the reason was easy to miss
                  until after Reject had already been clicked. */}
              {(selected.status === 'pending' || selected.status === 'approved') && (
                <input className="input input-sm" placeholder="Optional rejection reason"
                  value={rejectReason} onChange={e => setRejectReason(e.target.value)} />
              )}

              <div className="aqp-actions">
                {selected.status === 'pending' && (
                  <button className="btn btn-solid btn-sm" disabled={busy}
                    onClick={() => runAction(selected.id, () => approveAndApply(selected.id))}>
                    Approve &amp; apply
                  </button>
                )}
                {selected.status === 'pending' && (
                  <button className="btn btn-outline btn-sm" disabled={busy}
                    onClick={() => runAction(selected.id, () => api.approvals.approve(selected.id))}>
                    Approve
                  </button>
                )}
                {selected.status === 'approved' && (
                  <button className="btn btn-solid btn-sm" disabled={busy}
                    onClick={() => runAction(selected.id, () => api.approvals.apply(selected.id))}>
                    Apply
                  </button>
                )}
                {(selected.status === 'pending' || selected.status === 'approved') && (
                  <button className="btn btn-destructive btn-sm" disabled={busy}
                    onClick={() => runAction(selected.id, () => api.approvals.reject(selected.id, rejectReason || undefined))}>
                    Reject
                  </button>
                )}
                {['pending', 'approved', 'failed'].includes(selected.status) && (
                  <button className="btn btn-outline btn-sm" disabled={busy}
                    onClick={() => runAction(selected.id, () => api.approvals.invalidate(selected.id))}>
                    Invalidate
                  </button>
                )}
              </div>

              {actionError && <p className="aqp-state aqp-error">{actionError}</p>}

              <h4 className="aqp-audit-title">Audit timeline</h4>
              <ul className="aqp-audit">
                {audit.map(e => (
                  <li key={e.id}>
                    <span className="aqp-audit-event">{e.event_type}</span>
                    <span className="aqp-audit-actor" title={e.actor_display ? e.actor_type : undefined}>
                      {e.actor_display ?? e.actor_type}
                    </span>
                    <span className="aqp-audit-time" title={e.created_at}>{fmtTimestamp(e.created_at)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
