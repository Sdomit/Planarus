import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import AgentRunsPanel from './AgentRunsPanel'

afterEach(cleanup)

const run = {
  id: 'run_1',
  project_id: 'proj_1',
  agent_family: 'claude',
  agent_name: 'claude-fable-5',
  mode: 'implement',
  status: 'started',
  summary: 'Working on phase 9',
  started_at: '2026-07-10T12:00:00+00:00',
  ended_at: null,
  created_at: 't',
  updated_at: 't',
}

const analytics = {
  project_id: 'proj_1',
  generated_at: 't',
  total: 3,
  by_family: { claude: 2, codex: 1 },
  by_status: { succeeded: 1, failed: 1, started: 1 },
  by_mode: { implement: 1 },
  success_rate: 0.5,
  avg_duration_minutes: 20,
  last_run_at: '2026-07-10T12:00:00+00:00',
}

const update = vi.fn(async () => ({ ...run, status: 'succeeded' }))
const create = vi.fn(async () => run)

vi.mock('../api/client', () => ({
  api: {
    agentRuns: {
      list: vi.fn(async () => [run]),
      analytics: vi.fn(async () => analytics),
      create: (...args: unknown[]) => create(...(args as [])),
      update: (...args: unknown[]) => update(...(args as [])),
    },
  },
}))

describe('AgentRunsPanel', () => {
  it('shows analytics tiles and the runs list', async () => {
    render(<AgentRunsPanel projectId="proj_1" />)
    expect(await screen.findByText('Total runs')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText('50%')).toBeTruthy()
    expect(screen.getByText('20 min')).toBeTruthy()
    expect(screen.getByText('Working on phase 9')).toBeTruthy()
  })

  it('marks a started run as succeeded', async () => {
    render(<AgentRunsPanel projectId="proj_1" />)
    const doneBtn = await screen.findByText('✓ done')
    fireEvent.click(doneBtn)
    await waitFor(() => expect(update).toHaveBeenCalledWith('run_1', { status: 'succeeded' }))
  })

  it('logs a new run', async () => {
    render(<AgentRunsPanel projectId="proj_1" />)
    await screen.findByText('Log an agent run')
    fireEvent.click(screen.getByText('Log run'))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith('proj_1', {
        agent_family: 'claude',
        mode: null,
        agent_name: null,
        summary: null,
      }),
    )
  })
})
