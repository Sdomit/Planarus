import { useEffect, useRef, useState } from 'react'
import Dashboard from './Dashboard'
import CockpitPanel from './CockpitPanel'
import PlanningPanel from './PlanningPanel'
import RoadmapPanel from './RoadmapPanel'
import TimelinePanel from './TimelinePanel'
import DocsPanel from './DocsPanel'
import ContextPackBuilder from './ContextPackBuilder'
import ContextFilesPanel from './ContextFilesPanel'
import MarkdownPreviewPanel from './MarkdownPreviewPanel'
import ApprovalQueuePanel from './ApprovalQueuePanel'
import ExternalClientsPanel from './ExternalClientsPanel'
import AgentRunsPanel from './AgentRunsPanel'
import RemindersPanel from './RemindersPanel'
import NotificationsBell from './NotificationsBell'
import { Icon } from './Icon'
import './layout.css'

type MainView =
  | 'dashboard' | 'cockpit' | 'planning' | 'roadmap' | 'timeline' | 'docs'
  | 'context-pack' | 'context-files' | 'preview' | 'approvals' | 'clients'
  | 'agent-runs' | 'reminders'

interface SelectedProject {
  id: string
  title: string
  slug: string
}

const NAV: { group: string; items: { view: MainView; label: string; icon: string }[] }[] = [
  { group: 'Workspace', items: [
    { view: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { view: 'cockpit', label: 'Cockpit', icon: 'zap' },
    { view: 'planning', label: 'Planning', icon: 'layers' },
    { view: 'roadmap', label: 'Roadmap', icon: 'columns' },
    { view: 'timeline', label: 'Timeline', icon: 'clock' },
  ] },
  { group: 'Context', items: [
    { view: 'docs', label: 'Docs', icon: 'file' },
    { view: 'context-pack', label: 'Context Pack', icon: 'inbox' },
    { view: 'context-files', label: 'Context Files', icon: 'folder' },
    { view: 'preview', label: 'Markdown Preview', icon: 'code' },
  ] },
  { group: 'Agents', items: [
    { view: 'approvals', label: 'Approvals', icon: 'check' },
    { view: 'clients', label: 'Clients', icon: 'external' },
    { view: 'agent-runs', label: 'Agent Runs', icon: 'table' },
    { view: 'reminders', label: 'Reminders', icon: 'bell' },
  ] },
]

const TITLES: Record<MainView, { title: string; sub: string }> = {
  dashboard: { title: 'Dashboard', sub: 'Workspace overview' },
  cockpit: { title: 'Cockpit', sub: 'Project command center' },
  planning: { title: 'Planning', sub: 'Phases, tasks, decisions & risks' },
  roadmap: { title: 'Roadmap', sub: 'Progress across phases & stages' },
  timeline: { title: 'Timeline', sub: 'Audited project activity' },
  docs: { title: 'Docs', sub: 'Project documents' },
  'context-pack': { title: 'Context Pack', sub: 'Build an AI context pack' },
  'context-files': { title: 'Context Files', sub: 'Generated Markdown context' },
  preview: { title: 'Markdown Preview', sub: 'Rendered context files & docs' },
  approvals: { title: 'Approval Queue', sub: 'Pending agent proposals' },
  clients: { title: 'External API Clients', sub: 'Machine keys & scopes' },
  'agent-runs': { title: 'Agent Runs', sub: 'Execution telemetry & analytics' },
  reminders: { title: 'Reminders', sub: 'Email reminders & send history' },
}

function initials(s: string): string {
  return (
    s.replace(/[^a-zA-Z0-9 ]/g, '').split(/\s+/).filter(Boolean).slice(0, 2)
      .map((w) => w[0]).join('').toUpperCase() || 'AB'
  )
}

export default function Layout() {
  const [mainView, setMainView] = useState<MainView>('dashboard')
  const [project, setProject] = useState<SelectedProject | null>(null)
  const [theme, setTheme] = useState<string>(
    () => document.documentElement.getAttribute('data-theme') || 'light-blue',
  )
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuBtnRef = useRef<HTMLButtonElement>(null)

  const isDark = theme.startsWith('dark')
  const toggleTheme = () => {
    const next = isDark ? 'light-blue' : 'dark-blue'
    document.documentElement.setAttribute('data-theme', next)
    setTheme(next)
  }

  useEffect(() => {
    if (!mobileMenuOpen) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileMenuOpen(false)
        menuBtnRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [mobileMenuOpen])

  const closeMenu = () => setMobileMenuOpen(false)

  const navigate = (view: MainView) => {
    setMainView(view)
    closeMenu()
  }

  const selectProject = (p: SelectedProject) => {
    setProject(p)
    setMainView('cockpit')
    closeMenu()
  }

  const placeholder = (
    <div className="card" style={{ textAlign: 'center', padding: 'var(--space-10)' }}>
      <p style={{ color: 'var(--text-secondary)', marginTop: 0 }}>
        Select a project on the Dashboard first.
      </p>
      <button className="btn btn-solid btn-sm" type="button" onClick={() => setMainView('dashboard')}>
        Go to Dashboard
      </button>
    </div>
  )

  const { title, sub } = TITLES[mainView]

  return (
    <div className="ab-app">
      {mobileMenuOpen && (
        <div className="ab-menu-overlay" aria-hidden="true" onClick={closeMenu} />
      )}
      <aside id="ab-sidebar" className={`ab-sidebar${mobileMenuOpen ? ' ab-sidebar--open' : ''}`} data-theme="dark-blue">
        <div className="ab-brand">
          <div className="ab-brand-mark">A</div>
          <div>
            <div className="ab-brand-name">AgentBoard</div>
            <div className="ab-brand-env">local · :5173</div>
          </div>
        </div>

        <div className="ab-side-scroll">
          <button className="ab-projsel" type="button" onClick={() => { setMainView('dashboard'); closeMenu() }}>
            <span className="pj-mark">{project ? initials(project.title) : 'AB'}</span>
            <span className="pj-meta">
              <span className="pj-name">{project ? project.title : 'All projects'}</span>
              <span className="pj-sub">{project ? project.slug : 'Select a project'}</span>
            </span>
          </button>

          {NAV.map((grp) => (
            <nav className="sidebar-nav" aria-label={grp.group} key={grp.group}>
              <div className="sidebar-nav-label">{grp.group}</div>
              {grp.items.map((it) => {
                const active = mainView === it.view
                return (
                  <button
                    key={it.view}
                    type="button"
                    className={`sidebar-nav-item${active ? ' active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                    onClick={() => navigate(it.view)}
                  >
                    <Icon name={it.icon} className="nav-icon ic" />
                    <span>{it.label}</span>
                  </button>
                )
              })}
            </nav>
          ))}
        </div>

        <div className="ab-side-foot">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 6 }}>
            <span className="avatar avatar-sm" style={{ background: 'var(--accent-muted)', color: 'var(--text-accent)' }}>AB</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Local workspace</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Single-user</div>
            </div>
            <span className="live-dot" title="Connected" />
          </div>
        </div>
      </aside>

      <div className="ab-main">
        <header className="ab-topbar">
          <button
            ref={menuBtnRef}
            type="button"
            className="ab-menu-btn"
            aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={mobileMenuOpen}
            aria-controls="ab-sidebar"
            onClick={() => setMobileMenuOpen(v => !v)}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" aria-hidden="true">
              <rect y="3" width="18" height="2" rx="1" />
              <rect y="8" width="18" height="2" rx="1" />
              <rect y="13" width="18" height="2" rx="1" />
            </svg>
          </button>
          <div className="ab-tb-titles">
            <h1 className="ab-tb-title" style={{ margin: 0 }}>{title}</h1>
            <div className="ab-tb-sub">{sub}</div>
          </div>
          <div className="ab-tb-spacer" />
          <label className="ab-search">
            <Icon name="search" className="ic-14" />
            <input type="text" placeholder="Search…" aria-label="Search" />
            <kbd>⌘K</kbd>
          </label>
          <NotificationsBell projectId={project?.id ?? null} />
          <button className="ab-iconbtn" type="button" onClick={toggleTheme} aria-label="Toggle theme">
            <Icon name={isDark ? 'sun' : 'moon'} className="ic-18" />
          </button>
        </header>

        <main className="ab-content">
          <div className="ab-content-inner">
            <div style={{ minWidth: 0 }}>
              {mainView === 'dashboard' && <Dashboard onSelectProject={selectProject} />}
              {mainView === 'cockpit' && (project ? <CockpitPanel projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'planning' && (project ? <PlanningPanel projectId={project.id} /> : placeholder)}
              {mainView === 'roadmap' && (project ? <RoadmapPanel projectId={project.id} /> : placeholder)}
              {mainView === 'timeline' && (project ? <TimelinePanel projectId={project.id} /> : placeholder)}
              {mainView === 'docs' && (project ? <DocsPanel projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'context-pack' && (project ? <ContextPackBuilder projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'context-files' && (project ? <ContextFilesPanel projectId={project.id} /> : placeholder)}
              {mainView === 'preview' && (project ? <MarkdownPreviewPanel projectId={project.id} /> : placeholder)}
              {mainView === 'approvals' && (project ? <ApprovalQueuePanel projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'clients' && <ExternalClientsPanel onClose={() => setMainView('dashboard')} />}
              {mainView === 'agent-runs' && (project ? <AgentRunsPanel projectId={project.id} /> : placeholder)}
              {mainView === 'reminders' && (project ? <RemindersPanel projectId={project.id} /> : placeholder)}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
