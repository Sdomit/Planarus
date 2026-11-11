import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import AgentPromptsModal from './AgentPromptsModal'

vi.mock('../api/client', () => ({
  api: {
    projects: { list: () => Promise.resolve([
      { id: 'proj_new', title: 'New Team Project', workspace_id: 'ws_1', summary: 'Build together', status: 'planning', folder_path: 'C:\\work\\new-team' },
      { id: 'proj_other', title: 'Unrelated', workspace_id: 'ws_1' },
    ]) },
    integrations: { mcp: () => Promise.resolve({
      server_name: 'planarus', command: 'C:\\Python\\python.exe', args: ['-m', 'app.mcp.server'],
      cwd: 'C:\\Planarus\\apps\\api', database_url: 'sqlite:///C:/Planarus/data.db',
      capability_env: 'PLANARUS_MCP_CAPABILITY', read_tools: [], propose_tools: [],
    }) },
  },
}))

afterEach(cleanup)

describe('project-specific agent prompt', () => {
  it('copies exact project context and project-scoped Codex and Claude MCP configs', async () => {
    const writeText = vi.fn((_value: string) => Promise.resolve())
    Object.assign(navigator, { clipboard: { writeText } })
    render(<AgentPromptsModal currentProject={{ id: 'proj_new', title: 'New Team Project', workspace_id: 'ws_1', summary: 'Build together', status: 'planning', folder_path: 'C:\\work\\new-team' }} onClose={() => {}} onOpenSettings={() => {}} />)

    const prompt = screen.getByLabelText('Shared Planarus prompt') as HTMLTextAreaElement
    await waitFor(() => expect(prompt.value).toContain('"project_id": "proj_new"'))
    expect(prompt.value).toContain('Build together')
    expect(prompt.value).toContain('C:\\\\work\\\\new-team')
    expect(prompt.value).not.toContain('proj_other')
    fireEvent.click(await screen.findByRole('button', { name: 'Copy everything' }))
    const all = String(writeText.mock.lastCall?.[0])
    expect(all).toContain(prompt.value.trim())
    expect(all).toContain('~/.codex/config.toml')
    expect(all).toContain('mcpServers.planarus')
    expect(all).toContain('install-planarus-progress-hooks.py')
    expect(all).toContain('.planarus-progress.json')
    expect(all).toContain('list_status_options')
    expect(all).toContain('"project_id": "proj_new"')
    expect(all).not.toContain('proj_other')
    fireEvent.click(screen.getByRole('button', { name: 'Copy prompt' }))
    expect(writeText).toHaveBeenLastCalledWith(prompt.value)

    fireEvent.click(await screen.findByRole('button', { name: 'Copy Codex config' }))
    const codex = String(writeText.mock.lastCall?.[0])
    expect(codex).toContain('proj_new')
    expect(codex).not.toContain('proj_other')

    fireEvent.click(screen.getByRole('button', { name: 'Copy Claude config' }))
    const claude = JSON.parse(String(writeText.mock.lastCall?.[0]))
    const capability = JSON.parse(claude.mcpServers.planarus.env.PLANARUS_MCP_CAPABILITY)
    expect(capability).toMatchObject({ tier: 'propose', workspace_id: 'ws_1', project_ids: ['proj_new'], label: 'claude' })
  })
})
