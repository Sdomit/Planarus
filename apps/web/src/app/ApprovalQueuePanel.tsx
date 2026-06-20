import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type ApprovalAuditEntry,
  type ApprovalDetail,
  type ApprovalSummary,
} from '../api/client'
import './approval-queue-panel.css'

const OPEN_STATES = ['pending', 'approved', 'applying']

interface ApprovalQueuePanelProps {
  projectId: string
  onClose: () => void
}

function targetLabel(a: ApprovalSummary): string {
  if (a.target_entity_id) {
    return `${a.target_entity_type}:${a.target_entity_id.slice(0, 14)}`
  }
  return `new ${a.target_entity_type ?? 'entity'}`
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return '∅'
  if (typeof v === 'string') return v === '' ? '(empty)' : v
  return JSON.stringify(v)
}

export default function ApprovalQueuePanel({ projectId, onClose }: ApprovalQueuePanelProps) {
  const [items, setItems] = useState<ApprovalSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selected, setSelected] = useState<ApprovalDetail | null>(null)
  const [audit, setAudit] = useState<ApprovalAuditEntry[]>([])
  const [detailError, setDetailError] = useState<string | null>(null)

  const [rejectReason, setRejectReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadList = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    return api.approvals
      .list(projectId)
      .then(setItems)
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    loadList()
  }, [loadList])

  const openDetail = useCallback((id: string) => {
    setDetailError(null)
    setActionError(null)
    setRejectReason('')
    Promise.all([api.approvals.get(id), api.approvals.audit(id)])
      .then(([d, a]) => {
        setSelected(d)
        setAudit(a)
      })
      .catch((e: Error) => setDetailError(e.message))
  }, [])

  const runAction = useCallback(
    (id: string, fn: () => Promise<ApprovalSummary>) => {
      setBusy(true)
      setActionError(null)
      fn()
        .then((updated) => {
          setSelected((prev) => (prev ? { ...prev, ...updated } : prev))
          setItems((prev) =>
            prev.map((it) => (it.id === updated.id ? { ...it, ...updated } : it)),
          )
          api.approvals.audit(id).then(setAudit).catch(() => undefined)
        })
        .catch((e: Error) => setActionError(e.message))
        .finally(() => setBusy(false))
    },
    [],
  )

  const pending = items.filter((a) => OPEN_STATES.includes(a.status))
  const history = items.filter((a) => !OPEN_STATES.includes(a.status))

  const renderRow = (a: ApprovalSummary) => (
    <button
      key={a.id}
      type="button"
      className={
        selected?.id === a.id ? 'aqp-row aqp-row-selected' : 'aqp-row'
      }
      onClick={() => openDetail(a.id)}
    >
      <span className={`aqp-origin aqp-origin-${a.origin}`}>{a.origin}</span>
      <span className="aqp-row-action">{a.action_type}</span>
      <span className="aqp-row-target">{targetLabel(a)}</span>
      <span className={`aqp-risk aqp-risk-${a.risk_level}`}>{a.risk_level}</span>
      <span className={`aqp-status aqp-status-${a.status}`}>{a.status}</span>
    </button>
  )

  return (
    <div className="aqp-panel">
      <div className="aqp-header">
        <span className="aqp-title">Approval Queue</span>
        <button className="aqp-close" onClick={onClose} title="Close">
          ✕
        </button>
      </div>

      <p className="aqp-notice" role="note">
        Proposals are reference-only until you approve and apply them. AgentBoard
        never applies a change on its own.
      </p>

      <div className="aqp-body">
        <div className="aqp-list">
          {loading && <p className="aqp-state">Loading approvals…</p>}
          {loadError && <p className="aqp-state aqp-error">{loadError}</p>}
          {!loading && !loadError && (
            <>
              <section className="aqp-section">
                <h3 className="aqp-section-title">Pending ({pending.length})</h3>
                {pending.length === 0 ? (
                  <p className="aqp-empty">No pending proposals.</p>
                ) : (
                  pending.map(renderRow)
                )}
              </section>
              <section className="aqp-section">
                <h3 className="aqp-section-title">History ({history.length})</h3>
                {history.length === 0 ? (
                  <p className="aqp-empty">No decided proposals yet.</p>
                ) : (
                  history.map(renderRow)
                )}
              </section>
            </>
          )}
        </div>

        <div className="aqp-detail">
          {detailError && <p className="aqp-state aqp-error">{detailError}</p>}
          {!selected ? (
            <p className="aqp-empty">Select a proposal to review it.</p>
          ) : (
            <>
              <div className="aqp-detail-head">
                <span className="aqp-detail-action">{selected.action_type}</span>
                <span className={`aqp-status aqp-status-${selected.status}`}>
                  {selected.status}
                </span>
              </div>
              <dl className="aqp-meta">
                <div>
                  <dt>Origin</dt>
                  <dd>{selected.origin}</dd>
                </div>
                <div>
                  <dt>Project</dt>
                  <dd>{selected.project_id}</dd>
                </div>
                <div>
                  <dt>Target</dt>
                  <dd>{targetLabel(selected)}</dd>
                </div>
                <div>
                  <dt>Risk</dt>
                  <dd>{selected.risk_level}</dd>
                </div>
                <div>
                  <dt>Expires</dt>
                  <dd>{selected.expires_at}</dd>
                </div>
                <div>
                  <dt>Checksum</dt>
                  <dd className="aqp-checksum">{selected.patch_checksum.slice(0, 16)}</dd>
                </div>
              </dl>

              {selected.is_expired && (
                <p className="aqp-warn" role="alert">
                  ⚠ This proposal has expired and can no longer be applied.
                </p>
              )}
              {selected.stale_reason && (
                <p className="aqp-warn" role="alert">
                  ⚠ Stale: {selected.stale_reason}. Applying will be blocked; a new
                  proposal is required.
                </p>
              )}
              <p className="aqp-secret-note">
                🔒 Secrets are blocked at proposal time (best-effort); patch content
                is never logged or audited.
              </p>

              <h4 className="aqp-diff-title">Proposed change (before → after)</h4>
              {selected.diff.length === 0 ? (
                <p className="aqp-empty">No fields.</p>
              ) : (
                <ul className="aqp-diff">
                  {selected.diff.map((d) => (
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
                Approving allows AgentBoard to apply only this exact proposal once.
              </p>

              <div className="aqp-actions">
                {selected.status === 'pending' && (
                  <button
                    className="aqp-btn aqp-approve"
                    disabled={busy}
                    onClick={() => runAction(selected.id, () => api.approvals.approve(selected.id))}
                  >
                    Approve
                  </button>
                )}
                {selected.status === 'approved' && (
                  <button
                    className="aqp-btn aqp-apply"
                    disabled={busy}
                    onClick={() => runAction(selected.id, () => api.approvals.apply(selected.id))}
                  >
                    Apply
                  </button>
                )}
                {(selected.status === 'pending' || selected.status === 'approved') && (
                  <button
                    className="aqp-btn aqp-reject"
                    disabled={busy}
                    onClick={() =>
                      runAction(selected.id, () =>
                        api.approvals.reject(selected.id, rejectReason || undefined),
                      )
                    }
                  >
                    Reject
                  </button>
                )}
                {['pending', 'approved', 'failed'].includes(selected.status) && (
                  <button
                    className="aqp-btn aqp-invalidate"
                    disabled={busy}
                    onClick={() =>
                      runAction(selected.id, () => api.approvals.invalidate(selected.id))
                    }
                  >
                    Invalidate
                  </button>
                )}
              </div>
              {(selected.status === 'pending' || selected.status === 'approved') && (
                <input
                  className="aqp-reject-reason"
                  placeholder="Optional rejection reason"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
              )}
              {actionError && <p className="aqp-state aqp-error">{actionError}</p>}

              <h4 className="aqp-audit-title">Audit timeline</h4>
              <ul className="aqp-audit">
                {audit.map((e) => (
                  <li key={e.id}>
                    <span className="aqp-audit-event">{e.event_type}</span>
                    <span className="aqp-audit-actor">{e.actor_type}</span>
                    <span className="aqp-audit-time">{e.created_at}</span>
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
