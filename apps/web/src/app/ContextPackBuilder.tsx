import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type ContextPackPreview,
  type ContextPackProfilesResponse,
  type ContextPackSelection,
  type ContextPackSources,
} from '../api/client'
import './context-pack-builder.css'

const OPTIONAL_FLAG: Record<string, keyof OptionalFlags> = {
  tasks_done: 'include_done_tasks',
  risks_closed: 'include_closed_risks',
  blockers_resolved: 'include_resolved_blockers',
  decisions_extra: 'include_all_decisions',
  audit_recent: 'include_audit_slice',
}

interface OptionalFlags {
  include_done_tasks: boolean
  include_closed_risks: boolean
  include_resolved_blockers: boolean
  include_all_decisions: boolean
  include_audit_slice: boolean
}

const EMPTY_FLAGS: OptionalFlags = {
  include_done_tasks: false,
  include_closed_risks: false,
  include_resolved_blockers: false,
  include_all_decisions: false,
  include_audit_slice: false,
}

interface ContextPackBuilderProps { projectId: string; onClose: () => void }

export default function ContextPackBuilder({ projectId }: ContextPackBuilderProps) {
  const [profilesData, setProfilesData] = useState<ContextPackProfilesResponse | null>(null)
  const [sources, setSources] = useState<ContextPackSources | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [profile, setProfile] = useState('build')
  const [targetTool, setTargetTool] = useState('claude-sonnet-4-6')
  const [budget, setBudget] = useState('medium')
  const [objective, setObjective] = useState('')

  const [excluded, setExcluded] = useState<Set<string>>(new Set())
  const [optionals, setOptionals] = useState<OptionalFlags>(EMPTY_FLAGS)
  const [selectedDocs, setSelectedDocs] = useState<string[]>([])
  const [pinned, setPinned] = useState<Set<string>>(new Set())

  const [preview, setPreview] = useState<ContextPackPreview | null>(null)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [govBlock, setGovBlock] = useState<string | null>(null)

  const [showCopyConfirm, setShowCopyConfirm] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setLoadError(null)
    Promise.all([api.contextPack.profiles(), api.contextPack.sources(projectId)])
      .then(([p, s]) => { if (!cancelled) { setProfilesData(p); setSources(s) } })
      .catch((e: Error) => !cancelled && setLoadError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [projectId])

  const buildSelection = useCallback((): ContextPackSelection => ({
    document_ids: selectedDocs,
    document_order: selectedDocs,
    pinned_source_ids: [...pinned],
    excluded_source_ids: [...excluded],
    ...optionals,
  }), [selectedDocs, pinned, excluded, optionals])

  const liveEstimate = useMemo(() => {
    if (!sources) return 0
    let t = 0
    for (const s of sources.structured) {
      if (s.default_included && !excluded.has(s.source_id)) t += s.token_estimate
      if (s.optional && optionals[OPTIONAL_FLAG[s.source_id]]) t += s.token_estimate
    }
    for (const d of sources.documents) {
      if (selectedDocs.includes(d.doc_id)) t += d.token_estimate
    }
    return t
  }, [sources, excluded, optionals, selectedDocs])

  // #98: the API refuses with 409 when a governance file is excluded, rather than
  // returning a pack whose "authoritative" scope section is empty. Surface that
  // as a decision — fix it in Context files, or say so and generate anyway.
  const generate = useCallback((allowIncompleteGovernance = false) => {
    setGenerating(true); setGenError(null); setGovBlock(null)
    setCopied(false); setShowCopyConfirm(false)
    api.contextPack
      .preview(projectId, {
        profile, target_tool: targetTool, budget_preset: budget, objective,
        selection: buildSelection(),
        allow_incomplete_governance: allowIncompleteGovernance,
      })
      .then(setPreview)
      .catch((e: Error) => {
        if (e.message.startsWith('409:')) setGovBlock(e.message)
        else setGenError(e.message)
      })
      .finally(() => setGenerating(false))
  }, [projectId, profile, targetTool, budget, objective, buildSelection])

  const confirmCopy = useCallback(() => {
    if (preview && navigator.clipboard?.writeText) navigator.clipboard.writeText(preview.markdown)
    setCopied(true); setShowCopyConfirm(false)
  }, [preview])

  const toggleStructured = (sourceId: string, isOptional: boolean) => {
    if (isOptional) {
      const flag = OPTIONAL_FLAG[sourceId]
      setOptionals(o => ({ ...o, [flag]: !o[flag] }))
    } else {
      setExcluded(prev => {
        const next = new Set(prev)
        if (next.has(sourceId)) next.delete(sourceId); else next.add(sourceId)
        return next
      })
    }
  }

  const toggleDoc = (docId: string) =>
    setSelectedDocs(prev => prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId])

  const togglePin = (sourceId: string) =>
    setPinned(prev => {
      const next = new Set(prev)
      if (next.has(sourceId)) next.delete(sourceId); else next.add(sourceId)
      return next
    })

  const moveDoc = (docId: string, dir: -1 | 1) =>
    setSelectedDocs(prev => {
      const i = prev.indexOf(docId), j = i + dir
      if (i < 0 || j < 0 || j >= prev.length) return prev
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]]
      return next
    })

  if (loading) return <p className="cpb-state">Loading sources…</p>
  if (loadError) return <p className="cpb-state" style={{ color: 'var(--status-danger-fg)' }}>{loadError}</p>
  if (!profilesData || !sources) return <p className="cpb-state">No data available.</p>

  return (
    <div className="cpb-panel">
      <p className="cpb-notice" role="note">
        🔒 Packs are local — nothing is sent anywhere until you copy it.
      </p>

      <div className="cpb-layout">
        {/* Left: controls */}
        <div className="cpb-controls">
          <div className="cpb-field">
            <label className="cpb-field-label">Profile</label>
            <select className="input select" value={profile} onChange={e => setProfile(e.target.value)}>
              {profilesData.profiles.map(p => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>

          <div className="cpb-field">
            <label className="cpb-field-label">Target tool</label>
            <select className="input select" value={targetTool} onChange={e => setTargetTool(e.target.value)}>
              {profilesData.target_tools.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div className="cpb-field">
            <label className="cpb-field-label">Budget</label>
            <select className="input select" value={budget} onChange={e => setBudget(e.target.value)}>
              {Object.entries(profilesData.budget_presets).map(([k, v]) => (
                <option key={k} value={k}>{k} (~{v.toLocaleString()} tok)</option>
              ))}
            </select>
          </div>

          <div className="cpb-field">
            <label className="cpb-field-label">
              Your task <span style={{ fontWeight: 400, color: 'var(--text-tertiary)' }}>(authoritative — kept separate from project data)</span>
            </label>
            <textarea className="input" placeholder="Describe the single task you want the agent to do…"
              value={objective} onChange={e => setObjective(e.target.value)} rows={3} />
          </div>

          <div className="cpb-srcgroup">
            <div className="cpb-srcgroup-head">
              <span className="cpb-srcgroup-title">Project sources</span>
            </div>
            {sources.structured.map(s => {
              const checked = s.optional ? optionals[OPTIONAL_FLAG[s.source_id]] : !excluded.has(s.source_id)
              return (
                <label key={s.source_id} className={`ab-src${checked ? ' on' : ''}`}>
                  <input type="checkbox" checked={checked} onChange={() => toggleStructured(s.source_id, s.optional)}
                    style={{ flexShrink: 0 }} />
                  <span className="ab-src-name">{s.label}</span>
                  <span className="ab-src-tok">{s.kind}</span>
                  <span className="ab-src-tok">~{s.token_estimate}</span>
                </label>
              )
            })}
          </div>

          <div className="cpb-srcgroup">
            <div className="cpb-srcgroup-head">
              <span className="cpb-srcgroup-title">Documents</span>
            </div>
            {sources.documents.length === 0 ? (
              <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', margin: 0 }}>No documents in this project.</p>
            ) : sources.documents.map(d => {
              const sel = selectedDocs.includes(d.doc_id)
              const isPinned = pinned.has(d.source_id)
              return (
                <div key={d.doc_id} className="cpb-doc-row">
                  <label className={`ab-src${sel ? ' on' : ''}`}>
                    <input type="checkbox" checked={sel} onChange={() => toggleDoc(d.doc_id)} style={{ flexShrink: 0 }} />
                    <span className="ab-src-name">{d.title}</span>
                    <span className="ab-src-tok">~{d.token_estimate}</span>
                  </label>
                  {sel && (
                    <div className="cpb-doc-actions">
                      <button type="button" className="btn btn-ghost btn-xs"
                        onClick={() => togglePin(d.source_id)} title={isPinned ? 'Unpin' : 'Pin (trimmed last)'}>
                        {isPinned ? '📌' : '📌'}{isPinned ? ' Pinned' : ' Pin'}
                      </button>
                      <button type="button" className="btn btn-ghost btn-xs" onClick={() => moveDoc(d.doc_id, -1)} title="Move up">↑</button>
                      <button type="button" className="btn btn-ghost btn-xs" onClick={() => moveDoc(d.doc_id, 1)} title="Move down">↓</button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <div className="cpb-estimate">
            Estimated: <strong>~{liveEstimate.toLocaleString()}</strong> tokens (approximate)
          </div>

          <button className="btn btn-solid" onClick={() => generate()} disabled={generating}>
            {generating ? 'Generating…' : 'Generate preview'}
          </button>
          {genError && <p className="cpb-error-msg">{genError}</p>}
          {govBlock && (
            <div className="cpb-gov-block" role="alert">
              <p className="cpb-error-msg">
                <strong>Scope section would be incomplete.</strong>{' '}
                {govBlock.replace(/^409:\s*/, '').replace(/^\{"detail":"?/, '').replace(/"?\}$/, '')}
              </p>
              <p className="cpb-gov-hint">
                Accept the edit on the <strong>Context files</strong> tab to include it, or
                generate a pack that says the scope is unavailable.
              </p>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => generate(true)}
                disabled={generating}
              >
                Generate anyway
              </button>
            </div>
          )}
        </div>

        {/* Right: preview */}
        <div className="cpb-preview">
          {!preview ? (
            <div className="cpb-empty">Choose your sources and click "Generate preview".</div>
          ) : (
            <>
              <div className="cpb-preview-meta">
                <span className={`cpb-tokens${preview.over_budget ? ' over' : ''}`}>
                  ~{preview.token_estimate.toLocaleString()} / {preview.budget_limit.toLocaleString()} tokens
                  {preview.over_budget ? ' ⚠ over budget' : ''}
                </span>
                <span className="cpb-checksum" title="Pack checksum">{preview.pack_checksum.slice(0, 12)}</span>
              </div>

              {preview.warnings.length > 0 && (
                <ul className="cpb-warnings">
                  {preview.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
                </ul>
              )}

              {preview.truncations.length > 0 && (
                <p className="cpb-trunc">
                  Trimmed {preview.truncations.length} source(s) to fit budget:{' '}
                  {preview.truncations.map(t => `${t.source_id} (${t.reason})`).join(', ')}
                </p>
              )}

              {preview.secret_findings.length > 0 && (
                <div className="cpb-secrets" role="alert">
                  <strong>Possible secrets (masked, best-effort):</strong>
                  <ul>
                    {preview.secret_findings.map((f, i) => (
                      <li key={i}>{f.pattern_label}: <code>{f.masked_preview}</code> in {f.source_ref} ×{f.count}</li>
                    ))}
                  </ul>
                </div>
              )}

              <pre className="ab-preview-body cpb-markdown">{preview.markdown}</pre>

              <div className="cpb-actions">
                <button className="btn btn-outline btn-sm" onClick={() => setShowCopyConfirm(true)}>
                  Copy to clipboard
                </button>
                {copied && <span className="cpb-copied">Copied ✓</span>}
              </div>

              {showCopyConfirm && (
                <div className="cpb-confirm-dialog" role="dialog" aria-label="Copy confirmation">
                  <p>
                    This pack will leave Planarus when you paste it into an external tool.
                    {preview.secret_findings.length > 0
                      ? ` ${preview.secret_findings.length} possible secret(s) were flagged (detection is best-effort).`
                      : ' Secret detection is best-effort and not a guarantee.'}
                  </p>
                  <div className="cpb-confirm-actions">
                    <button className="btn btn-solid btn-sm" onClick={confirmCopy}>Copy anyway</button>
                    <button className="btn btn-outline btn-sm" onClick={() => setShowCopyConfirm(false)}>Cancel</button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
