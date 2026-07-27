import { useEffect, useState, type CSSProperties } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router'
import { api, type DocSummary } from '../api/client'
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
 * rather than guessing — an unresolvable doc slug gets the same treatment,
 * once the project's doc list has actually loaded (#183 step 3c).
 */
export default function ProjectRoute() {
  const { workspaceSlug, projectSlug, view: viewParam, approvalId, taskId, docSlug } = useParams()
  const navigate = useNavigate()
  const [state, setState] = useState<ResolveState>({ status: 'loading' })

  // #183 step 3c: /docs/:docSlug needs the project's doc list to map a slug to
  // an id (and back, when a selection changes the URL) — docs have no by-slug
  // read endpoint, so this resolves the same way the workspace/project slugs
  // above do. Fetched only while the docs view is actually active.
  const [docs, setDocs] = useState<DocSummary[] | null>(null)
  const project = state.status === 'ready' ? state.project : null
  const view: MainView = approvalId
    ? 'approvals'
    : taskId
      ? 'planning'
      : docSlug
        ? 'docs'
        : viewParam === undefined
          ? 'cockpit'
          : (viewParam as MainView)

  useEffect(() => {
    if (!project || view !== 'docs') { setDocs(null); return }
    let cancelled = false
    api.docs.list(project.id).then(ds => {
      if (!cancelled) setDocs(ds)
    })
    return () => {
      cancelled = true
    }
  }, [project, view])

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

  if (viewParam !== undefined && !isProjectScopedView(viewParam)) {
    // Unknown segment, or one of dashboard/settings/team typed onto a project
    // URL by hand — neither belongs here. Redirect rather than guess.
    return <Navigate to={projectPath(state.project)} replace />
  }
  // A doc slug that matches nothing once the list has actually loaded — typo,
  // deleted doc — gets the same "redirect to the view's own home" treatment
  // as an unrecognised :view segment above, rather than sitting on a dead URL.
  if (docSlug && docs !== null && !docs.some(d => d.slug === docSlug)) {
    return <Navigate to={`${projectPath(state.project)}/docs`} replace />
  }

  const detailId = approvalId ?? taskId ?? (docSlug ? docs?.find(d => d.slug === docSlug)?.id : undefined)

  const onNavigate = (nextView: MainView, nextProject: SelectedProject) => {
    if (nextView === 'dashboard') return navigate('/')
    if (nextView === 'settings') return navigate('/settings')
    if (nextView === 'team') return navigate('/team')
    const base = projectPath(nextProject)
    navigate(nextView === 'cockpit' ? base : `${base}/${nextView}`)
  }

  // Which nested detail shape applies depends on the *current* view — each
  // of the three (approvals -> tasks -> docs) gets its own URL segment.
  const onSelectDetail = (id: string | null) => {
    const base = projectPath(state.project)
    if (view === 'approvals') return navigate(id ? `${base}/approvals/${id}` : `${base}/approvals`)
    if (view === 'planning') return navigate(id ? `${base}/planning/task/${id}` : `${base}/planning`)
    if (view === 'docs') {
      if (!id) return navigate(`${base}/docs`)
      const slug = docs?.find(d => d.id === id)?.slug
      return navigate(slug ? `${base}/docs/${slug}` : `${base}/docs`)
    }
  }

  return <Layout routed={{ project: state.project, view, onNavigate, detailId, onSelectDetail }} />
}
