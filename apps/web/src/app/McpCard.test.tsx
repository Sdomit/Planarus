import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import McpCard from './McpCard'

vi.mock('../api/client', () => ({
  api: {
    integrations: {
      mcp: vi.fn(async () => ({
        server_name: 'agentboard',
        command: 'python',
        args: ['-m', 'app.mcp.server'],
        cwd: '/home/me/apps/api',
        capability_env: 'AGENTBOARD_MCP_CAPABILITY',
        read_tools: [{ name: 'list_projects', description: 'List projects.' }],
        propose_tools: [{ name: 'create_task_proposal', description: 'Propose a task.' }],
      })),
    },
    workspaces: { list: vi.fn(async () => [{ id: 'ws_1', name: 'WS' }]) },
    projects: { list: vi.fn(async () => [{ id: 'proj_1', title: 'P1' }, { id: 'proj_2', title: 'P2' }]) },
  },
}))

afterEach(cleanup)

describe('McpCard', () => {
  it('generates a paste-ready JSON config scoped to the workspace projects', async () => {
    render(<McpCard />)
    // Wait until the async scope (projects) is folded into the config.
    await waitFor(() => expect(screen.getByText(/mcpServers/).textContent).toContain('proj_2'))
    const cfg = screen.getByText(/mcpServers/).textContent ?? ''
    expect(cfg).toContain('app.mcp.server')       // launch module
    expect(cfg).toContain('/home/me/apps/api')     // real cwd from the endpoint
    expect(cfg).toContain('AGENTBOARD_MCP_CAPABILITY')
    expect(cfg).toContain('proj_1')                // both projects → zero hand-editing
  })

  it('switches to the Claude Code CLI form', async () => {
    render(<McpCard />)
    await waitFor(() => screen.getByText(/mcpServers/))
    fireEvent.click(screen.getByRole('tab', { name: 'Claude Code CLI' }))
    expect(screen.getByText(/claude mcp add agentboard/)).toBeTruthy()
  })

  it('adds propose tools to the catalog when access is read+propose', async () => {
    render(<McpCard />)
    await waitFor(() => screen.getByText(/Tools this grants \(1\)/))
    fireEvent.change(screen.getByLabelText('Access'), { target: { value: 'propose' } })
    await waitFor(() => expect(screen.getByText(/Tools this grants \(2\)/)).toBeTruthy())
    // The generated capability tier flips too.
    expect(screen.getByText(/mcpServers/).textContent).toContain('propose')
  })
})
