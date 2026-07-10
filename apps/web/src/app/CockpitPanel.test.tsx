import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import CockpitPanel from './CockpitPanel'
import { api } from '../api/client'

const project = { id: 'proj_1', title: 'Demo', slug: 'demo', status: 'active', summary: 'A demo' }

const gitRepo = {
  project_id: 'proj_1', repo_path: '/srv/demo', is_repo: true,
  current_branch: 'main', detached: false, last_commit_sha: 'abc1234',
  last_commit_subject: 'initial commit', is_dirty: true, dirty_count: 2,
  remote_url: 'https://example.com/x.git', message: null, checked_at: 't',
}

vi.mock('../api/client', () => ({
  api: {
    projects: { get: vi.fn(async () => project) },
    phases: { list: vi.fn(async () => [{ id: 'ph_1' }]) },
    tasks: { list: vi.fn(async () => [{ id: 't_1', status: 'in_progress' }, { id: 't_2', status: 'done' }]) },
    risks: { list: vi.fn(async () => [{ id: 'r_1', status: 'open' }]) },
    git: { get: vi.fn(async () => gitRepo) },
    approvals: { list: vi.fn(async () => []) },
  },
}))

/** Read the numeric value of a KPI tile by its label. */
function kpiValue(container: HTMLElement, label: string): string | undefined {
  const labelEl = Array.from(container.querySelectorAll('.ab-kpi-label')).find(
    (el) => el.textContent === label,
  )
  return labelEl?.closest('.ab-kpi')?.querySelector('.ab-kpi-val')?.textContent ?? undefined
}

describe('CockpitPanel', () => {
  it('renders the project header, computed KPIs and the Git summary', async () => {
    const { container } = render(<CockpitPanel projectId="proj_1" onClose={() => {}} />)
    expect(await screen.findByText('Demo')).toBeTruthy()
    // Git summary surfaces branch, commit, and dirty state.
    expect(screen.getByText('main')).toBeTruthy()
    expect(screen.getByText('abc1234')).toBeTruthy()
    expect(screen.getByText('initial commit')).toBeTruthy()
    expect(screen.getByText('2 uncommitted')).toBeTruthy()
    // KPI math: 1 open task of 2 total; 1 open risk.
    expect(kpiValue(container, 'Open tasks')).toBe('1')
    expect(kpiValue(container, 'Open risks')).toBe('1')
  })

  it('degrades gracefully when the Git read fails', async () => {
    vi.mocked(api.git.get).mockRejectedValueOnce(new Error('boom'))
    const { container } = render(<CockpitPanel projectId="proj_1" onClose={() => {}} />)
    // Header + KPIs still render (the four required calls succeeded)…
    expect(await screen.findByText('Demo')).toBeTruthy()
    await waitFor(() => expect(kpiValue(container, 'Open tasks')).toBe('1'))
    // …and the Git card shows the fallback rather than crashing the panel.
    expect(screen.getByText('No Git metadata available.')).toBeTruthy()
  })
})
