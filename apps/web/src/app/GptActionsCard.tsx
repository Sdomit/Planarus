import { useEffect, useState } from 'react'
import { api, type OpenApiContract } from '../api/client'
import CopyButton from './CopyButton'

// P17.5: ChatGPT / GPT Actions card. Fetches the curated contract from
// /integrations/gpt-openapi (a mirror of app/api/external/openapi.py) and, given
// the user's public tunnel host, finalizes the servers URL so the schema pastes
// into ChatGPT with zero editing. The setup tunnel forwards only /api/external/*,
// so this is copy-paste, not import-from-URL.

type Profile = 'readonly' | 'read_propose'

const codeBlock: React.CSSProperties = {
  display: 'block',
  whiteSpace: 'pre',
  overflow: 'auto',
  maxHeight: 240,
  background: 'var(--bg-subtle)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 'var(--text-xs)',
  margin: 0,
}

function schemaText(contract: OpenApiContract, host: string): string {
  const clean = host.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')
  const finalized = clean
    ? { ...contract, servers: [{ url: `https://${clean}/api/external/v1`, description: 'Your public HTTPS host (Cloudflare tunnel).' }] }
    : contract
  return JSON.stringify(finalized, null, 2)
}

function exposureLabel(active: boolean, permitted: boolean, hostsConfigured: boolean): string {
  if (!permitted) return 'not permitted by environment'
  if (!hostsConfigured) return 'no public host allow-listed'
  if (!active) return 'switched off'
  return 'ready'
}

export default function GptActionsCard(
  { active, permitted, hostsConfigured }: { active: boolean; permitted: boolean; hostsConfigured: boolean },
) {
  const [profile, setProfile] = useState<Profile>('readonly')
  const [host, setHost] = useState('')
  const [contract, setContract] = useState<OpenApiContract | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.integrations.gptOpenapi(profile).then(setContract).catch((e: Error) => setError(e.message))
  }, [profile])

  const exposure = exposureLabel(active, permitted, hostsConfigured)

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>ChatGPT (GPT Actions)</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Connect a private “Only me” GPT — read-only, and it can never approve or apply. Paste the
        schema below into the GPT’s Actions, and authenticate with a scoped <code>agbk_</code> key.
      </p>

      <p style={{ fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Exposure:{' '}
        <strong style={{ color: exposure === 'ready' ? 'var(--status-success-fg, var(--text-primary))' : 'var(--text-secondary)' }}>
          {exposure}
        </strong>
        {exposure !== 'ready' && (
          <span style={{ color: 'var(--text-tertiary)' }}> — see the External API section &amp; the setup guide.</span>
        )}
      </p>

      <div className="tabs" role="tablist" aria-label="Contract profile" style={{ borderBottom: 'none', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <button type="button" role="tab" aria-selected={profile === 'readonly'} className={`tab${profile === 'readonly' ? ' active' : ''}`} onClick={() => setProfile('readonly')}>Read-only (recommended)</button>
        <button type="button" role="tab" aria-selected={profile === 'read_propose'} className={`tab${profile === 'read_propose' ? ' active' : ''}`} onClick={() => setProfile('read_propose')}>Read + propose</button>
      </div>
      {profile === 'read_propose' && (
        <p style={{ color: 'var(--status-warning-fg, var(--text-tertiary))', fontSize: 'var(--text-xs)', margin: '0 0 var(--space-3)' }}>
          ⚠ The read+propose contract is gated — don’t import it for a first live GPT.
        </p>
      )}

      <div className="form-field" style={{ marginBottom: 'var(--space-3)' }}>
        <label className="form-label" htmlFor="gpt-host">Public HTTPS host (optional — pre-fills the schema’s server URL)</label>
        <input id="gpt-host" className="input input-sm" placeholder="planarus.example.com" value={host} onChange={e => setHost(e.target.value)} />
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      {contract && (
        <div className="form-field">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)' }}>OpenAPI schema — paste into ChatGPT → Actions</span>
            <CopyButton text={schemaText(contract, host)} label="Copy schema" />
          </div>
          <code style={codeBlock}>{schemaText(contract, host)}</code>
        </div>
      )}

      <ol style={{ margin: 'var(--space-4) 0 0', paddingLeft: 'var(--space-5)', display: 'grid', gap: 4, fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
        <li>Create a <strong>read-only</strong> <code>agbk_</code> key (one project) in the <strong>API Keys</strong> tab.</li>
        <li>Put Planarus behind an HTTPS tunnel — see <code>docs/guide/connect-planarus-to-chatgpt.md</code>.</li>
        <li>ChatGPT → create a GPT (<strong>Only me</strong>) → Actions → paste the schema → Auth: Bearer, your key.</li>
      </ol>
    </section>
  )
}
