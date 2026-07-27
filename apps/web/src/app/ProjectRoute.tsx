import { useEffect, useState, type CSSProperties } from 'react'
import { useParams } from 'react-router'
import { api } from '../api/client'
import { EmptyState } from './EmptyState'
import Layout, { type SelectedProject } from './Layout'

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

/**
 * #183 step 1 — resolves `/w/:workspaceSlug/p/:projectSlug` to a project, then
 * mounts Layout with it as the initial selection. Layout itself stays
 * router-agnostic (no `useParams`/`useNavigate` inside it); this component is
 * the only place a URL param is read, so Layout's existing tests (which
 * render it with no router context) are unaffected.
 *
 * A slug that matches nothing — deleted project, mistyped link, wrong
 * workspace — falls back to a plain "go to Dashboard" state rather than a
 * silent misfile onto some other project (the same rule #106's capture intake
 * follows for an unresolvable clip).
 */
export default function ProjectRoute() {
  const { workspaceSlug, projectSlug } = useParams()
  const [state, setState] = useState<ResolveState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    api.workspaces
      .list()
      .then((workspaces) => {
        const ws = workspaces.find((w) => w.slug === workspaceSlug)
        if (!ws) throw new Error('workspace not found')
        return api.projects.list(ws.id)
      })
      .then((projects) => {
        const p = projects.find((p) => p.slug === projectSlug)
        if (!p) throw new Error('project not found')
        if (!cancelled) setState({ status: 'ready', project: { id: p.id, title: p.title, slug: p.slug } })
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
  return <Layout initialProject={state.project} initialView="cockpit" />
}
