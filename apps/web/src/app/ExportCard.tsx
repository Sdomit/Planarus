import { useEffect, useRef, useState } from 'react'
import { api, type Project, type Workspace } from '../api/client'

// P17.6b: Export / import a project as portable JSON. Backend does the graph
// walk + id remap (GET /projects/{id}/export, POST /projects/import); this card
// just triggers a download and reads an uploaded file.

function downloadJson(filename: string, obj: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function ExportCard() {
  const [projects, setProjects] = useState<Project[]>([])
  const [exportId, setExportId] = useState('')
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [importWs, setImportWs] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [imported, setImported] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.projects.list()
      .then(ps => { setProjects(ps); if (ps[0]) setExportId(ps[0].id) })
      .catch((e: Error) => setError(e.message))
    api.workspaces.list()
      .then(ws => { setWorkspaces(ws); if (ws[0]) setImportWs(ws[0].id) })
      .catch((e: Error) => setError(e.message))
  }, [])

  const doExport = () => {
    if (!exportId) return
    setError(null)
    const proj = projects.find(p => p.id === exportId)
    api.projects.export(exportId)
      .then(data => downloadJson(`${proj?.slug || 'project'}.planarus.json`, data))
      .catch((e: Error) => setError(e.message))
  }

  const doImport = () => {
    const file = fileRef.current?.files?.[0]
    if (!file || !importWs) return
    setBusy(true)
    setError(null)
    setImported(null)
    file.text()
      .then(text => api.projects.import(importWs, JSON.parse(text)))
      .then(proj => { setImported(proj.title); if (fileRef.current) fileRef.current.value = '' })
      .catch((e: Error) => setError(/JSON/.test(e.message) ? 'That file is not valid JSON.' : e.message))
      .finally(() => setBusy(false))
  }

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>Export &amp; import</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Move a project between Planarus instances as portable JSON — its planning graph (phases, tasks,
        decisions, docs, comments…), with ids remapped on import. History, approvals, and webhooks stay
        with the original. “Get my data out” is part of connecting to anything.
      </p>

      <div className="form-field">
        <label className="form-label" htmlFor="exp-proj">Export a project</label>
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <select id="exp-proj" className="input select input-sm" style={{ flex: 1, minWidth: 200 }} value={exportId} onChange={e => setExportId(e.target.value)} disabled={projects.length === 0}>
            {projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select>
          <button type="button" className="btn btn-outline btn-sm" onClick={doExport} disabled={!exportId}>Download JSON</button>
        </div>
      </div>

      <div className="form-field" style={{ marginTop: 'var(--space-3)' }}>
        <label className="form-label" htmlFor="imp-ws">Import into workspace</label>
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}>
          <select id="imp-ws" className="input select input-sm" value={importWs} onChange={e => setImportWs(e.target.value)} disabled={workspaces.length === 0}>
            {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <input ref={fileRef} type="file" accept="application/json,.json" aria-label="Export file" className="input input-sm" style={{ flex: 1, minWidth: 180 }} />
          <button type="button" className="btn btn-solid btn-sm" onClick={doImport} disabled={busy || !importWs}>{busy ? 'Importing…' : 'Import'}</button>
        </div>
      </div>

      {imported && (
        <p style={{ color: 'var(--status-success-fg, var(--text-secondary))', fontSize: 'var(--text-sm)', margin: 'var(--space-2) 0 0' }}>
          Imported “{imported}” as a new project ✓
        </p>
      )}
      {error && <p className="form-error" role="alert" style={{ marginTop: 'var(--space-2)' }}>{error}</p>}
    </section>
  )
}
