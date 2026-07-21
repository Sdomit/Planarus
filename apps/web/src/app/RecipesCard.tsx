import CopyButton from './CopyButton'

// P17.5: docs-as-cards. Copy-paste starters that drive Planarus from a pipeline
// via the external API — they ride on the API Keys + REST cards, no new backend.

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

// Plain-string array so GitHub's ${{ … }} expression syntax stays literal.
const GH_ACTIONS = [
  '# .github/workflows/planarus.yml — read Planarus project status from CI',
  'name: planarus-status',
  'on: [workflow_dispatch]',
  'jobs:',
  '  status:',
  '    runs-on: ubuntu-latest',
  '    steps:',
  '      - name: List Planarus projects',
  '        run: |',
  '          curl -sS \\',
  '            -H "Authorization: Bearer ${{ secrets.PLANARUS_API_KEY }}" \\',
  '            "${{ vars.PLANARUS_BASE_URL }}/projects"',
].join('\n')

export default function RecipesCard() {
  return (
    <section>
      <h3 style={{ marginTop: 0 }}>Recipes (CI &amp; automation)</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-3)' }}>
        Starters that drive Planarus from a pipeline via the external API. Store the key as a secret
        (never commit it) and set <code>PLANARUS_BASE_URL</code> to your public <code>…/api/external/v1</code> host.
      </p>
      <div className="form-field">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)' }}>GitHub Actions — read project status</span>
          <CopyButton text={GH_ACTIONS} label="Copy workflow" />
        </div>
        <code style={codeBlock}>{GH_ACTIONS}</code>
      </div>
      <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', margin: 'var(--space-3) 0 0' }}>
        n8n / Zapier / Make: add an HTTP Request node — <code>GET {'{base}'}/projects</code> with an{' '}
        <code>Authorization: Bearer agbk_…</code> header. Same key, same read / propose scope.
      </p>
    </section>
  )
}
