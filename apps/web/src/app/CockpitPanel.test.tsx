import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import CockpitPanel from './CockpitPanel'
import { api } from '../api/client'

const project = { id: 'proj_1', title: 'Demo', slug: 'demo', status: 'active', summary: 'A demo' }

// Phase 12a repo cockpit snapshot (rendered by GitSnapshotPanel inside the cockpit).
const gitSnapshot = {
  project_id: 'proj_1', repo_path: '/srv/demo', is_repo: true, message: null, checked_at: 't',
  current_branch: 'main', detached: false, default_branch: 'main',
  last_commit_sha: 'abc1234', last_commit_subject: 'initial commit',
  remote_url: 'https://example.com/x.git',
  branches: [
    { name: 'main', is_current: true, upstream: 'origin/main', ahead: 1, behind: 0, gone: false, committed_at: '2026-07-17T10:00:00Z', ahead_of_default: 0, behind_default: 0 },
    { name: 'feat/x', is_current: false, upstream: null, ahead: null, behind: null, gone: false, committed_at: '2026-07-16T10:00:00Z', ahead_of_default: 2, behind_default: 1 },
  ],
  branches_total: 2,
  needs_merge: ['feat/x'],
  working_tree: { staged: 1, unstaged: 1, untracked: 0, conflicted: 0, ahead: 1, behind: 0 },
  last_fetched_at: null,
}

vi.mock('../api/client', () => ({
  api: {
    projects: { get: vi.fn(async () => project) },
    phases: { list: vi.fn(async () => [{ id: 'ph_1' }]) },
    tasks: { list: vi.fn(async () => [{ id: 't_1', status: 'in_progress' }, { id: 't_2', status: 'done' }]) },
    risks: { list: vi.fn(async () => [{ id: 'r_1', status: 'open' }]) },
    milestones: { list: vi.fn(async () => []) },
    decisions: { list: vi.fn(async () => []) },
    git: { snapshot: vi.fn(async () => gitSnapshot), fetchNow: vi.fn() },
    approvals: {
      list: vi.fn(async () => []),
      listPaged: vi.fn(async () => ({ items: [], total: 0, hasMore: false })),
    },
    // #95: the cockpit now also reads open blockers and the UNSCOPED feed for the
    // "Needs attention" widget.
    blockers: { list: vi.fn(async () => []) },
    notifications: { feed: vi.fn(async () => ({ generated_at: 't', items: [] })) },
    roadmap: { get: vi.fn(async () => ({ project_id: 'p', generated_at: 't', phases: [], unphased: { total: 0, done: 0, in_progress: 0, blocked: 0 }, totals: { total: 0, done: 0, in_progress: 0, blocked: 0 }, pct_done: 0 })) },
    timeline: { get: vi.fn(async () => ({ project_id: 'p', generated_at: 't', events: [] })) },
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
  it('renders the project header, computed KPIs and the repo snapshot', async () => {
    const { container } = render(<CockpitPanel projectId="proj_1" onClose={() => {}} onOpenCanvas={() => {}} />)
    expect(await screen.findByText('Demo')).toBeTruthy()
    // Repo snapshot surfaces commit, working-tree counts, needs-merge and the
    // always-visible freshness stamp.
    expect(await screen.findByText('abc1234')).toBeTruthy()
    expect(screen.getByText('initial commit')).toBeTruthy()
    expect(screen.getByText('1 staged · 1 unstaged')).toBeTruthy()
    expect(screen.getAllByText('feat/x').length).toBeGreaterThan(0)
    expect(screen.getByText('no fetch recorded — remote state may be stale')).toBeTruthy()
    // KPI math: 1 open task of 2 total; 1 open risk.
    expect(kpiValue(container, 'Open tasks')).toBe('1')
    expect(kpiValue(container, 'Open risks')).toBe('1')
  })

  it('degrades gracefully when the Git read fails', async () => {
    vi.mocked(api.git.snapshot).mockRejectedValueOnce(new Error('boom'))
    const { container } = render(<CockpitPanel projectId="proj_1" onClose={() => {}} onOpenCanvas={() => {}} />)
    // Header + KPIs still render (the required calls succeeded)…
    expect(await screen.findByText('Demo')).toBeTruthy()
    await waitFor(() => expect(kpiValue(container, 'Open tasks')).toBe('1'))
    // …and the Git card shows the fallback rather than crashing the panel.
    expect(await screen.findByText('No Git metadata available.')).toBeTruthy()
  })
})
