import { useEffect, useState, type CSSProperties } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import { EmptyState } from './EmptyState'
import Layout, { isProjectScopedView, type MainView, type SelectedProject } from './Layout'

const FULL_PAGE_CENTER: CSSProperties = {
  minHeight: '100dvh',
  display: 'grid',
  placeItems: 'center',
  background: 'var(--bg-canvas)',
  padding: 'var(--space-4)',
}

type ResolveState =
  | { status: 'loading' }
  | { status: 'ready'; project: SelectedProject }
  | { status: 'not-found' }

function projectPath(project: SelectedProject): string {
  return `/w/${project.workspaceSlug}/p/${project.slug}`
}

/**
 * #183 steps 1-2 — resolves `/w/:workspaceSlug/p/:projectSlug[/:view]` to a
 * project (+ one of the 14 project-scoped views; bare = cockpit), then mounts
 * Layout in *routed* mode: the URL is the source of truth for project/view,
 * and every Layout-internal navigation calls back here to push a new one.
 *
 * Layout itself stays router-agnostic (no `useParams`/`useNavigate` inside
 * it) — this component is the only place a URL param is read or a route is
 * pushed, so Layout's existing tests (which render it with no router
 * context) are unaffected by any of this.
 *
 * A slug that matches nothing — deleted project, mistyped link, wrong
 * workspace — falls back to a plain "go to Dashboard" state rather than a
 * silent misfile onto some other project (the same rule #106's capture
 * intake follows for an unresolvable clip). An unrecognised :view segment
 * (typo, or one of the three routes that deliberately live outside this
 * family — dashboard/settings/team) redirects to the project's own home
 * rather than guessing.
 */
export default function ProjectRoute() {
  const { workspaceSlug, projectSlug, view: viewParam } = useParams()
  const navigate = useNavigate()
  const [state, setState] = useState<ResolveState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    api.workspaces
      .list()
      .then((workspaces) => {
        const ws = workspaces.find((w) => w.slug === workspaceSlug)
        if (!ws) throw new Error('workspace not found')
        return api.projects.list(ws.id).then((projects) => ({ ws, projects }))
      })
      .then(({ ws, projects }) => {
        const p = projects.find((p) => p.slug === projectSlug)
        if (!p) throw new Error('project not found')
        if (!cancelled) {
          setState({
            status: 'ready',
            project: { id: p.id, title: p.title, slug: p.slug, workspaceSlug: ws.slug },
          })
        }
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'not-found' })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceSlug, projectSlug])

  if (state.status === 'loading') {
    return <div style={FULL_PAGE_CENTER} aria-busy="true" aria-live="polite" />
  }
  if (state.status === 'not-found') {
    return (
      <div style={FULL_PAGE_CENTER}>
        <EmptyState
          title="No project matches this link"
          hint="The project may have been renamed, deleted, or the link may be mistyped."
          action={{ label: 'Go to Dashboard', onClick: () => window.location.assign('/') }}
        />
      </div>
    )
  }

  const { project } = state
  const view: MainView = viewParam === undefined ? 'cockpit' : (viewParam as MainView)
  if (viewParam !== undefined && !isProjectScopedView(viewParam)) {
    // Unknown segment, or one of dashboard/settings/team typed onto a project
    // URL by hand — neither belongs here. Redirect rather than guess.
    return <Navigate to={projectPath(project)} replace />
  }

  const onNavigate = (nextView: MainView, nextProject: SelectedProject) => {
    if (nextView === 'dashboard') return navigate('/')
    if (nextView === 'settings') return navigate('/settings')
    if (nextView === 'team') return navigate('/team')
    const base = projectPath(nextProject)
    navigate(nextView === 'cockpit' ? base : `${base}/${nextView}`)
  }

  return <Layout routed={{ project, view, onNavigate }} />
}
