import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import ProjectRoute from './ProjectRoute'

const workspaces = vi.fn()
const projects = vi.fn()
vi.mock('../api/client', () => ({
  api: {
    workspaces: { list: (...args: unknown[]) => workspaces(...args) },
    projects: { list: (...args: unknown[]) => projects(...args) },
  },
}))

// ProjectRoute's job is resolving the URL to a project and handing off — its
// own contract, not Layout's (Layout.test.tsx covers Layout). Stub it to a
// thin probe of the two props ProjectRoute is responsible for passing.
vi.mock('./Layout', () => ({
  default: ({ initialProject, initialView }: { initialProject?: { title: string }; initialView?: string }) => (
    <div data-testid="layout-stub">
      {initialProject?.title} / {initialView}
    </div>
  ),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/w/:workspaceSlug/p/:projectSlug" element={<ProjectRoute />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectRoute', () => {
  it('resolves workspace + project slugs and mounts Layout with them', async () => {
    workspaces.mockResolvedValue([{ id: 'ws1', slug: 'acme' }])
    projects.mockResolvedValue([{ id: 'p1', slug: 'launch', title: 'Launch' }])

    renderAt('/w/acme/p/launch')

    expect(screen.queryByTestId('layout-stub')).toBeNull()
    await waitFor(() => expect(screen.getByTestId('layout-stub')).toBeTruthy())
    expect(screen.getByTestId('layout-stub').textContent).toBe('Launch / cockpit')
    expect(projects).toHaveBeenCalledWith('ws1')
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
