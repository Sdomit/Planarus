import { useEffect, useState } from 'react'
import { api, type McpInfo, type Workspace } from '../api/client'
import CopyButton from './CopyButton'

// P17.2: MCP config generator + live tool catalog for the Integrations tab.
// The launch command, real cwd, and tool list come from GET /integrations/mcp
// (sourced from app/mcp/registry.py — D37, can't drift). The scope is built into
// a valid AGENTBOARD_MCP_CAPABILITY JSON grant, so the emitted config needs zero
// hand-editing. The capability is a local scope declaration, not a secret.

type Fmt = 'json' | 'cli'
type Tier = 'read' | 'propose'

const CWD_PLACEHOLDER = '<path to your apps/api directory>'

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

function capabilityJson(tier: Tier, workspaceId: string, projectIds: string[]): string {
  return JSON.stringify({ tier, workspace_id: workspaceId, project_ids: projectIds, label: 'mcp' })
}

function jsonConfig(info: McpInfo, cap: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        [info.server_name]: {
          command: info.command,
          args: info.args,
          cwd: info.cwd ?? CWD_PLACEHOLDER,
          env: { [info.capability_env]: cap },
        },
      },
    },
    null,
    2,
  )
}

function cliConfig(info: McpInfo, cap: string): string {
  return [
    `# run this from ${info.cwd ?? CWD_PLACEHOLDER}`,
    `claude mcp add ${info.server_name} \\`,
    `  --env ${info.capability_env}='${cap}' \\`,
    `  -- ${info.command} ${info.args.join(' ')}`,
  ].join('\n')
}

export default function McpCard() {
  const [info, setInfo] = useState<McpInfo | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState('')
  const [projectIds, setProjectIds] = useState<string[]>([])
  const [tier, setTier] = useState<Tier>('read')
  const [fmt, setFmt] = useState<Fmt>('json')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.integrations.mcp().then(setInfo).catch((e: Error) => setError(e.message))
    api.workspaces.list()
      .then(ws => { setWorkspaces(ws); if (ws[0]) setWorkspaceId(ws[0].id) })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!workspaceId) { setProjectIds([]); return }
    api.projects.list(workspaceId)
      .then(ps => setProjectIds(ps.map(p => p.id)))
      .catch((e: Error) => setError(e.message))
  }, [workspaceId])

  if (error) return <section><h3 style={{ marginTop: 0 }}>MCP</h3><p className="form-error" role="alert">{error}</p></section>
  if (!info) return <section><h3 style={{ marginTop: 0 }}>MCP</h3><p style={{ color: 'var(--text-tertiary)' }}>Loading…</p></section>

  const cap = capabilityJson(tier, workspaceId, projectIds)
  const config = fmt === 'json' ? jsonConfig(info, cap) : cliConfig(info, cap)
  const catalog = tier === 'propose' ? [...info.read_tools, ...info.propose_tools] : info.read_tools
  const remoteUrl = `${typeof window !== 'undefined' ? window.location.origin : ''}/api/external/v1/mcp`

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>MCP (local agents)</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Connect a local agent (Claude Code, Claude Desktop, Cursor, Windsurf, VS Code) over STDIO.
        Pick a scope; the config below is paste-ready — read &amp; pending-proposal only, never approve or apply.
      </p>

      <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap', marginBottom: 'var(--space-3)' }}>
        <div className="form-field">
          <label className="form-label" htmlFor="mcp-tier">Access</label>
          <select id="mcp-tier" className="input select input-sm" value={tier} onChange={e => setTier(e.target.value as Tier)}>
            <option value="read">Read only</option>
            <option value="propose">Read + propose</option>
          </select>
        </div>
        <div className="form-field">
          <label className="form-label" htmlFor="mcp-ws">Workspace</label>
          <select
            id="mcp-ws"
            className="input select input-sm"
            value={workspaceId}
            onChange={e => setWorkspaceId(e.target.value)}
            disabled={workspaces.length === 0}
          >
            {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </div>
      </div>

      <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', margin: '0 0 var(--space-3)' }}>
        {projectIds.length > 0
          ? `Scoped to all ${projectIds.length} project${projectIds.length === 1 ? '' : 's'} in this workspace.`
          : 'This workspace has no projects yet — add one to scope the MCP grant.'}
        {info.cwd === null && ' Set the config’s cwd to your local apps/api directory.'}
      </p>

      <div className="form-field">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
          <div className="tabs" role="tablist" aria-label="Config format" style={{ borderBottom: 'none', gap: 'var(--space-3)' }}>
            <button type="button" role="tab" aria-selected={fmt === 'json'} className={`tab${fmt === 'json' ? ' active' : ''}`} onClick={() => setFmt('json')}>JSON config</button>
            <button type="button" role="tab" aria-selected={fmt === 'cli'} className={`tab${fmt === 'cli' ? ' active' : ''}`} onClick={() => setFmt('cli')}>Claude Code CLI</button>
          </div>
          <CopyButton text={config} label="Copy config" />
        </div>
        <code style={codeBlock}>{config}</code>
      </div>

      <div className="form-field" style={{ marginTop: 'var(--space-4)' }}>
        <label className="form-label">Remote (HTTP) — claude.ai / hosted connectors</label>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
          <code style={{ flex: 1, minWidth: 220, wordBreak: 'break-all', background: 'var(--bg-subtle)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '6px var(--space-3)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
            {remoteUrl}
          </code>
          <CopyButton text={remoteUrl} />
        </div>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', margin: 'var(--space-2) 0 0' }}>
          Authenticate with an <code>agbk_</code> key from the API Keys tab (Bearer). Needs the
          External API enabled + an HTTPS tunnel (same setup as the ChatGPT card); tools are
          scope-gated by the key — read &amp; propose only.
        </p>
      </div>

      <details style={{ marginTop: 'var(--space-4)' }}>
        <summary style={{ cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)' }}>
          Tools this grants ({catalog.length})
        </summary>
        <ul style={{ margin: 'var(--space-2) 0 0', paddingLeft: 'var(--space-5)', display: 'grid', gap: 4 }}>
          {catalog.map(t => (
            <li key={t.name} style={{ fontSize: 'var(--text-xs)' }}>
              <code>{t.name}</code>{' — '}
              <span style={{ color: 'var(--text-tertiary)' }}>{t.description}</span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
