import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import GitSnapshotPanel from './GitSnapshotPanel'
import { api } from '../api/client'

const baseSnap = {
  project_id: 'proj_1', repo_path: '/srv/demo', is_repo: true, message: null, checked_at: 't',
  current_branch: 'main', detached: false, default_branch: 'main',
  last_commit_sha: 'abc1234', last_commit_subject: 'initial', remote_url: 'git@x/y.git',
  branches: [{ name: 'main', is_current: true, upstream: 'origin/main', ahead: 0, behind: 2, gone: false, committed_at: '2026-07-17T10:00:00Z', ahead_of_default: 0, behind_default: 0 }],
  branches_total: 1, needs_merge: [], working_tree: { staged: 0, unstaged: 0, untracked: 0, conflicted: 0, ahead: 0, behind: 2 },
  last_fetched_at: null,
}

vi.mock('../api/client', () => ({
  api: {
    git: { snapshot: vi.fn(), fetchNow: vi.fn(), prs: vi.fn() },
    links: { create: vi.fn() },
  },
}))

beforeEach(() => {
  vi.mocked(api.git.snapshot).mockResolvedValue({ ...baseSnap })
  vi.mocked(api.git.fetchNow).mockReset()
  vi.mocked(api.git.prs).mockReset()
  vi.mocked(api.links.create).mockReset()
})

afterEach(cleanup)  // unmount between tests so ambiguous queries stay unambiguous

describe('GitSnapshotPanel — Phase 12b fetch', () => {
  it('fetches on click, then shows the result and the refreshed stamp', async () => {
    vi.mocked(api.git.fetchNow).mockResolvedValue({
      project_id: 'proj_1', status: 'ok', message: null, remote: 'origin',
      snapshot: { ...baseSnap, last_fetched_at: '2026-07-17T14:00:00Z' },
    })
    render(<GitSnapshotPanel projectId="proj_1" />)
    const btn = await screen.findByRole('button', { name: /fetch now/i })
    // Before fetch: never-fetched stamp.
    expect(screen.getByText(/no fetch recorded/i)).toBeTruthy()
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText('Fetched from origin.')).toBeTruthy())
    expect(api.git.fetchNow).toHaveBeenCalledWith('proj_1')
    // Stamp updated from the returned snapshot.
    expect(screen.getByText(/remote state as of last fetch/i)).toBeTruthy()
  })

  it('surfaces a rate-limited / failed message without breaking the panel', async () => {
    vi.mocked(api.git.fetchNow).mockResolvedValue({
      project_id: 'proj_1', status: 'rate_limited', message: 'Fetched moments ago — try again in ~7s.', remote: 'origin', snapshot: { ...baseSnap },
    })
    render(<GitSnapshotPanel projectId="proj_1" />)
    fireEvent.click(await screen.findByRole('button', { name: /fetch now/i }))
    await waitFor(() => expect(screen.getByText(/try again in/i)).toBeTruthy())
    // Cockpit still shows the branch — the offline view is never blocked.
    expect(screen.getByText('abc1234')).toBeTruthy()
  })

  it('shows the disabled (409) error as a message', async () => {
    vi.mocked(api.git.fetchNow).mockRejectedValue(new Error('git fetch is disabled — set AGENTBOARD_GIT_FETCH_ENABLED=true'))
    render(<GitSnapshotPanel projectId="proj_1" />)
    fireEvent.click(await screen.findByRole('button', { name: /fetch now/i }))
    await waitFor(() => expect(screen.getByText(/disabled/i)).toBeTruthy())
  })
})

describe('GitSnapshotPanel — Phase 12c pull requests', () => {
  const pr = {
    number: 7, title: 'Add PR layer', state: 'OPEN', is_draft: false,
    head: 'feat/x', base: 'main', url: 'https://github.com/x/y/pull/7',
    author: 'sdomit', updated_at: '2026-07-17T12:00:00Z', review_decision: null,
  }

  it('loads PRs only on click and renders the rows', async () => {
    vi.mocked(api.git.prs).mockResolvedValue({
      project_id: 'proj_1', status: 'ok', authenticated: true, message: null,
      prs: [pr], checked_at: 't',
    })
    render(<GitSnapshotPanel projectId="proj_1" />)
    await screen.findByRole('button', { name: /load prs/i })
    expect(api.git.prs).not.toHaveBeenCalled() // never auto-loaded
    fireEvent.click(screen.getByRole('button', { name: /load prs/i }))
    await waitFor(() => expect(screen.getByText('Add PR layer')).toBeTruthy())
    expect(api.git.prs).toHaveBeenCalledWith('proj_1')
    expect(screen.getByRole('link', { name: '#7' }).getAttribute('href')).toBe(pr.url)
  })

  it('saves a PR as a project link via the existing links API', async () => {
    vi.mocked(api.git.prs).mockResolvedValue({
      project_id: 'proj_1', status: 'ok', authenticated: true, message: null,
      prs: [pr], checked_at: 't',
    })
    vi.mocked(api.links.create).mockResolvedValue({
      id: 'lnk_1', project_id: 'proj_1', entity_type: 'project', entity_id: 'proj_1',
      url: pr.url, title: 'PR #7 — Add PR layer', created_at: 't',
    })
    render(<GitSnapshotPanel projectId="proj_1" />)
    fireEvent.click(await screen.findByRole('button', { name: /load prs/i }))
    fireEvent.click(await screen.findByRole('button', { name: /add link/i }))
    await waitFor(() => expect(screen.getByText('linked ✓')).toBeTruthy())
    expect(api.links.create).toHaveBeenCalledWith('proj_1', {
      entity_type: 'project', entity_id: 'proj_1', url: pr.url, title: 'PR #7 — Add PR layer',
    })
  })

  it('surfaces the signed-out state without breaking the cockpit', async () => {
    vi.mocked(api.git.prs).mockResolvedValue({
      project_id: 'proj_1', status: 'no_auth', authenticated: false,
      message: 'gh is not signed in — run `gh auth login` in a terminal. Approvo never stores the credential.',
      prs: [], checked_at: 't',
    })
    render(<GitSnapshotPanel projectId="proj_1" />)
    fireEvent.click(await screen.findByRole('button', { name: /load prs/i }))
    await waitFor(() => expect(screen.getByText(/not signed in/i)).toBeTruthy())
    expect(screen.getByText('abc1234')).toBeTruthy() // offline cockpit intact
  })
})
