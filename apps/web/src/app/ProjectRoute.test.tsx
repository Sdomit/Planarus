import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import ProjectRoute from './ProjectRoute'

const workspaces = vi.fn()
const projects = vi.fn()
vi.mock('../api/client', () => ({
  api: {
    workspaces: { list: (...args: unknown[]) => workspaces(...args) },
    projects: { list: (...args: unknown[]) => projects(...args) },
  },
}))

type StubProject = { id: string; title: string; workspaceSlug: string; slug: string }
type RoutedProps = {
  routed?: {
    project: StubProject
    view: string
    onNavigate: (view: string, project: StubProject) => void
  }
}

let lastOnNavigate: ((view: string, project: StubProject) => void) | undefined

// ProjectRoute's job is resolving the URL to a project + view and wiring
// navigation — its own contract, not Layout's (Layout.test.tsx covers
// Layout). Stub it to a thin probe of the `routed` prop ProjectRoute builds.
vi.mock('./Layout', () => ({
  default: ({ routed }: RoutedProps) => {
    lastOnNavigate = routed?.onNavigate
    return (
      <div data-testid="layout-stub">
        {routed?.project.title} / {routed?.view}
      </div>
    )
  },
  isProjectScopedView: (v: string) =>
    [
      'cockpit', 'planning', 'roadmap', 'timeline', 'calendar', 'docs', 'notes',
      'canvas', 'context-pack', 'context-files', 'preview', 'approvals',
      'agent-runs', 'reminders',
    ].includes(v),
}))

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  lastOnNavigate = undefined
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <Routes>
        <Route path="/w/:workspaceSlug/p/:projectSlug" element={<ProjectRoute />} />
        <Route path="/w/:workspaceSlug/p/:projectSlug/:view" element={<ProjectRoute />} />
        <Route path="/" element={<div data-testid="dashboard-stub" />} />
        <Route path="/settings" element={<div data-testid="settings-stub" />} />
        <Route path="/team" element={<div data-testid="team-stub" />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectRoute — resolution', () => {
  it('resolves workspace + project slugs and mounts Layout at cockpit for the bare route', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])

    renderAt('/w/acme/p/launch')

    expect(screen.queryByTestId('layout-stub')).toBeNull()
    await waitFor(() => expect(screen.getByTestId('layout-stub')).toBeTruthy())
    expect(screen.getByTestId('layout-stub').textContent).toBe('Launch / cockpit')
    expect(projects).toHaveBeenCalledWith('ws1')
  })

  it('resolves the :view segment to a project-scoped view', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])

    renderAt('/w/acme/p/launch/planning')

    await waitFor(() => expect(screen.getByTestId('layout-stub').textContent).toBe('Launch / planning'))
  })

  it('redirects an unrecognised :view segment to the project home', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])

    renderAt('/w/acme/p/launch/not-a-real-view')

    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/w/acme/p/launch'))
  })

  it('redirects dashboard/settings/team typed onto a project URL to the project home', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])

    renderAt('/w/acme/p/launch/settings')

    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/w/acme/p/launch'))
  })

  it('falls back to a not-found state for an unknown workspace slug', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([])

    renderAt('/w/does-not-exist/p/launch')

    await waitFor(() => expect(screen.getByText('No project matches this link')).toBeTruthy())
    expect(projects).not.toHaveBeenCalled()
  })

  it('falls back to a not-found state for an unknown project slug in a real workspace', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])

    renderAt('/w/acme/p/does-not-exist')

    await waitFor(() => expect(screen.getByText('No project matches this link')).toBeTruthy())
  })

  it('falls back to a not-found state when the API rejects', async () => {
    workspaces.mockRejectedValue(new Error('network error'))

    renderAt('/w/acme/p/launch')

    await waitFor(() => expect(screen.getByText('No project matches this link')).toBeTruthy())
  })
})

describe('ProjectRoute — onNavigate', () => {
  async function ready() {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])
    renderAt('/w/acme/p/launch/planning')
    await waitFor(() => expect(screen.getByTestId('layout-stub')).toBeTruthy())
  }

  const project = { id: 'p1', title: 'Launch', slug: 'launch', workspaceSlug: 'acme' }

  it('navigates to the bare project path for cockpit', async () => {
    await ready()
    lastOnNavigate!('cockpit', project)
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/w/acme/p/launch'))
  })

  it('navigates to a nested path for any other project-scoped view', async () => {
    await ready()
    lastOnNavigate!('roadmap', project)
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/w/acme/p/launch/roadmap'))
  })

  it('navigates a project switch to the new project at the same view', async () => {
    await ready()
    lastOnNavigate!('planning', { id: 'p2', title: 'Other', slug: 'other', workspaceSlug: 'other-ws' })
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/w/other-ws/p/other/planning'))
  })

  it('navigates dashboard/settings/team to their own top-level routes, ignoring the project', async () => {
    await ready()
    lastOnNavigate!('dashboard', project)
    await waitFor(() => expect(screen.getByTestId('dashboard-stub')).toBeTruthy())
  })
})
