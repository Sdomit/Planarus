import { useState } from 'react'
import CopyButton from './CopyButton'

// P17.1: REST API connection card for the Integrations tab. Surface-only — it
// shows the honestly-reachable facts an external tool needs to connect, all
// derived client-side. Only `/api/*` is proxied to the backend (dev Vite +
// prod nginx), so we surface the external base + the unauthenticated info
// endpoint, never the app-root /docs or /openapi.json (unreachable at origin).

const KEY_PLACEHOLDER = 'agbk_<key_id>_<secret>'

type Lang = 'curl' | 'python' | 'ts'

const LANGS: { key: Lang; label: string }[] = [
  { key: 'curl', label: 'curl' },
  { key: 'python', label: 'Python' },
  { key: 'ts', label: 'TypeScript' },
]

function snippet(lang: Lang, baseUrl: string): string {
  const url = `${baseUrl}/projects`
  if (lang === 'curl') {
    return `curl -H "Authorization: Bearer ${KEY_PLACEHOLDER}" \\\n  ${url}`
  }
  if (lang === 'python') {
    return [
      'import requests',
      '',
      'r = requests.get(',
      `    "${url}",`,
      `    headers={"Authorization": "Bearer ${KEY_PLACEHOLDER}"},`,
      ')',
      'r.raise_for_status()',
      'print(r.json())',
    ].join('\n')
  }
  return [
    `const res = await fetch("${url}", {`,
    `  headers: { Authorization: "Bearer ${KEY_PLACEHOLDER}" },`,
    '})',
    'console.log(await res.json())',
  ].join('\n')
}

const codeBlock: React.CSSProperties = {
  display: 'block',
  whiteSpace: 'pre',
  overflowX: 'auto',
  background: 'var(--bg-subtle)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 'var(--text-xs)',
  margin: 0,
}

const urlRow: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2)',
  alignItems: 'center',
  flexWrap: 'wrap',
}

const inlineCode: React.CSSProperties = {
  flex: 1,
  minWidth: 220,
  wordBreak: 'break-all',
  background: 'var(--bg-subtle)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: '6px var(--space-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 'var(--text-xs)',
}

export default function RestApiCard({ active, permitted }: { active: boolean; permitted: boolean }) {
  const [lang, setLang] = useState<Lang>('curl')
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const hostname = typeof window !== 'undefined' ? window.location.hostname : ''
  const baseUrl = `${origin}/api/external/v1`
  const infoUrl = `${origin}/api/v1/info`
  const isLoopback = hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '::1'

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>REST API</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Point any pipeline, script, or agent at Planarus with a scoped key from the{' '}
        <strong>API Keys</strong> tab. Read &amp; pending-proposal only — external calls never approve or apply.
      </p>

      <p style={{ fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Status:{' '}
        <strong style={{ color: active && permitted ? 'var(--status-success-fg, var(--text-primary))' : 'var(--text-secondary)' }}>
          {!permitted ? 'inert (not permitted by environment)' : active ? 'active' : 'switched off'}
        </strong>
        {' · '}
        <span style={{ color: 'var(--text-tertiary)' }}>
          {isLoopback ? 'loopback — this machine only' : `bound to ${hostname} — reachable on this address`}
        </span>
      </p>

      <div className="form-field" style={{ marginBottom: 'var(--space-3)' }}>
        <label className="form-label">Base URL</label>
        <div style={urlRow}>
          <code style={inlineCode}>{baseUrl}</code>
          <CopyButton text={baseUrl} />
        </div>
      </div>

      <div className="form-field" style={{ marginBottom: 'var(--space-4)' }}>
        <label className="form-label">Liveness / version (no key needed)</label>
        <div style={urlRow}>
          <code style={inlineCode}>{infoUrl}</code>
          <CopyButton text={infoUrl} />
        </div>
      </div>

      <div className="form-field">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
          <div className="tabs" role="tablist" aria-label="Snippet language" style={{ borderBottom: 'none', gap: 'var(--space-3)' }}>
            {LANGS.map(l => (
              <button
                key={l.key}
                type="button"
                role="tab"
                aria-selected={lang === l.key}
                className={`tab${lang === l.key ? ' active' : ''}`}
                onClick={() => setLang(l.key)}
              >
                {l.label}
              </button>
            ))}
          </div>
          <CopyButton text={snippet(lang, baseUrl)} label="Copy snippet" />
        </div>
        <code style={codeBlock}>{snippet(lang, baseUrl)}</code>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', margin: 'var(--space-2) 0 0' }}>
          Replace <code>{KEY_PLACEHOLDER}</code> with a key from the API Keys tab. Interactive
          Swagger docs are served by the API itself at <code>/docs</code> in local dev.
        </p>
      </div>
    </section>
  )
}
