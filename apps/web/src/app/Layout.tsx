import { useEffect, useMemo, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react'
import Dashboard from './Dashboard'
import CockpitPanel from './CockpitPanel'
import PlanningPanel, { type TabKey as PlanningTabKey } from './PlanningPanel'
import RoadmapPanel from './RoadmapPanel'
import TimelinePanel from './TimelinePanel'
import CalendarPanel from './CalendarPanel'
import DocsPanel from './DocsPanel'
import CanvasPanel from './CanvasPanel'
import ContextPackBuilder from './ContextPackBuilder'
import ContextFilesPanel from './ContextFilesPanel'
import MarkdownPreviewPanel from './MarkdownPreviewPanel'
import ApprovalQueuePanel from './ApprovalQueuePanel'
import AgentRunsPanel from './AgentRunsPanel'
import RemindersPanel from './RemindersPanel'
import SettingsPanel from './SettingsPanel'
import TeamPanel from './TeamPanel'
import AboutModal from './AboutModal'
import NotificationsBell from './NotificationsBell'
import { SidebarTodos } from './SidebarTodos'
import { useAuthInfo } from './auth'
import { Icon } from './Icon'
import { api, type NotificationItem, type Project } from '../api/client'
import './layout.css'

type MainView =
  | 'dashboard' | 'cockpit' | 'planning' | 'roadmap' | 'timeline' | 'calendar' | 'docs'
  | 'notes' | 'canvas' | 'context-pack' | 'context-files' | 'preview' | 'approvals'
  | 'agent-runs' | 'reminders' | 'team' | 'settings'

interface SelectedProject {
  id: string
  title: string
  slug: string
}

/**
 * Where a notification row should land (#95).
 *
 * Every non-approval row used to go to the Tasks tab generally — including rows
 * about a blocker or a milestone, which live on other tabs — and none carried
 * the item it was about. The feed id is `kind:entity_id`, so the entity to
 * scroll to is already in hand. Pure, so the mapping is testable without
 * rendering the whole shell.
 */
export function notificationTarget(item: NotificationItem): {
  view: MainView
  planningTab?: PlanningTabKey
  focusEntityId?: string
} {
  const focusEntityId = item.id.slice(item.id.indexOf(':') + 1) || undefined
  if (item.kind.startsWith('approval_')) return { view: 'approvals' }
  if (item.kind === 'blocker_open')
    return { view: 'planning', planningTab: 'risks', focusEntityId }
  if (item.kind === 'milestone_missed')
    return { view: 'planning', planningTab: 'milestones', focusEntityId }
  return { view: 'planning', planningTab: 'tasks', focusEntityId }
}

const NAV: { group: string; items: { view: MainView; label: string; icon: string }[] }[] = [
  { group: 'Workspace', items: [
    { view: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { view: 'cockpit', label: 'Cockpit', icon: 'zap' },
    { view: 'canvas', label: 'Canvas', icon: 'palette' },
    { view: 'planning', label: 'Planning', icon: 'layers' },
    { view: 'roadmap', label: 'Roadmap', icon: 'columns' },
    { view: 'timeline', label: 'Timeline', icon: 'clock' },
    { view: 'calendar', label: 'Calendar', icon: 'calendar' },
    { view: 'notes', label: 'Notes', icon: 'edit' },
  ] },
  { group: 'Context', items: [
    { view: 'docs', label: 'Docs', icon: 'file' },
    { view: 'context-pack', label: 'Context Pack', icon: 'inbox' },
    { view: 'context-files', label: 'Context Files', icon: 'folder' },
    { view: 'preview', label: 'Markdown Preview', icon: 'code' },
  ] },
  { group: 'Approvals & Activity', items: [
    { view: 'approvals', label: 'Approvals', icon: 'check' },
    { view: 'agent-runs', label: 'Agent Runs', icon: 'table' },
    { view: 'reminders', label: 'Reminders', icon: 'bell' },
  ] },
  { group: 'System', items: [
    // 'team' is team-mode only — filtered out of nav + quick-nav in local mode.
    { view: 'team', label: 'Team', icon: 'users' },
    { view: 'settings', label: 'Settings', icon: 'settings' },
  ] },
]

// System lives in the account menu, not the sidebar nav — still reachable via Ctrl+K.
const ACCOUNT_MENU = NAV.find(g => g.group === 'System')!.items

function navGroups(teamMode: boolean) {
  if (teamMode) return NAV
  return NAV.map(g => ({ ...g, items: g.items.filter(it => it.view !== 'team') }))
}

function isMobileViewport(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 639px)').matches
}

const TITLES: Record<MainView, { title: string; sub: string }> = {
  dashboard: { title: 'Dashboard', sub: 'Workspace overview' },
  cockpit: { title: 'Cockpit', sub: 'Project command center' },
  planning: { title: 'Planning', sub: 'Phases, tasks, milestones & risks' },
  roadmap: { title: 'Roadmap', sub: 'Progress across phases & stages' },
  timeline: { title: 'Timeline', sub: 'Audited project activity' },
  calendar: { title: 'Calendar', sub: 'Events, milestones & due dates' },
  docs: { title: 'Docs', sub: 'Project documents' },
  notes: { title: 'Notes', sub: 'Quick rich-text notes' },
  canvas: { title: 'Canvas', sub: 'Project whiteboard' },
  'context-pack': { title: 'Context Pack', sub: 'Build an AI context pack' },
  'context-files': { title: 'Context Files', sub: 'Generated Markdown context' },
  preview: { title: 'Markdown Preview', sub: 'Rendered context files & docs' },
  approvals: { title: 'Approval Queue', sub: 'Pending agent proposals' },
  'agent-runs': { title: 'Agent Runs', sub: 'Execution telemetry & analytics' },
  reminders: { title: 'Reminders', sub: 'Email reminders & send history' },
  team: { title: 'Team', sub: 'People, roles & access' },
  settings: { title: 'Settings', sub: 'Connections & runtime switches' },
}

/** Close a popover on outside-click or Escape. Shared by the project + account menus. */
function useDismiss(
  open: boolean,
  ref: RefObject<HTMLElement | null>,
  setOpen: Dispatch<SetStateAction<boolean>>,
) {
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, ref, setOpen])
}

// Survive a refresh: the open view + selected project are the whole of navigation state.
const NAV_KEY = 'planarus.nav'
function loadNav(): { view?: MainView; project?: SelectedProject } {
  try {
    const saved = JSON.parse(localStorage.getItem(NAV_KEY) ?? '{}')
    // A view removed since the state was written would crash TITLES[] — fall back.
    return saved?.view in TITLES ? saved : { ...saved, view: undefined }
  } catch {
    return {}
  }
}

/** Two-letter brand fallback, matching the "P" of the sidebar brand mark. */
const MARK = 'PL'

function initials(s: string): string {
  return (
    s.replace(/[^a-zA-Z0-9 ]/g, '').split(/\s+/).filter(Boolean).slice(0, 2)
      .map((w) => w[0]).join('').toUpperCase() || MARK
  )
}

// The address a teammate types to reach this machine. The port comes from the
// browser; the IP has to come from the API, since a page served over loopback
// cannot see which adapter is on the LAN. Hidden when the box has no LAN route.
function LanAddress() {
  const [ip, setIp] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    api.info.get().then((i) => setIp(i.lan_ip)).catch(() => {})
  }, [])
  if (!ip) return null
  const url = `http://${ip}:${window.location.port || '80'}`
  return (
    <>
      {' · '}
      <button
        type="button"
        className="ab-brand-ip"
        title={`Copy ${url} — other devices can reach it only in LAN team mode`}
        onClick={() => void navigator.clipboard?.writeText(url).then(() => setCopied(true), () => {})}
      >
        {copied ? 'copied ✓' : 'ip'}
      </button>
    </>
  )
}

export default function Layout() {
  const { me, signOut } = useAuthInfo()
  const [mainView, setMainView] = useState<MainView>(() => loadNav().view ?? 'dashboard')
  const [project, setProject] = useState<SelectedProject | null>(() => loadNav().project ?? null)
  const [theme, setTheme] = useState<string>(
    () => document.documentElement.getAttribute('data-theme') || 'light-cosmo',
  )
  const [aboutOpen, setAboutOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [mobileNavMode, setMobileNavMode] = useState(isMobileViewport)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [planningTab, setPlanningTab] = useState<PlanningTabKey>('phases')
  // #95: which row Planning should scroll to and mark, when we got there from a
  // notification about one specific item.
  const [planningFocus, setPlanningFocus] = useState<string | undefined>(undefined)
  const [projMenuOpen, setProjMenuOpen] = useState(false)
  const [acctMenuOpen, setAcctMenuOpen] = useState(false)
  const [projects, setProjects] = useState<Project[] | null>(null)
  const menuBtnRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const projMenuRef = useRef<HTMLDivElement>(null)
  const acctMenuRef = useRef<HTMLDivElement>(null)

  const isDark = theme.startsWith('dark')
  const toggleTheme = () => {
    const next = isDark ? 'light-cosmo' : 'dark-cosmo'
    document.documentElement.setAttribute('data-theme', next)
    // Persist, or the choice silently reverts on the next load. The inline
    // script in index.html reads this key before first paint.
    try {
      localStorage.setItem('planarus.theme', next)
    } catch {
      /* private mode — the toggle still works for this session */
    }
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

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(max-width: 639px)')
    const update = () => setMobileNavMode(query.matches)
    update()
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])

  useEffect(() => {
    if (sidebarRef.current) sidebarRef.current.inert = mobileNavMode && !mobileMenuOpen
    if (mobileNavMode && mobileMenuOpen) {
      sidebarRef.current?.querySelector<HTMLButtonElement>('button')?.focus()
    }
  }, [mobileMenuOpen, mobileNavMode])

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchInputRef.current?.focus()
        setSearchOpen(true)
      }
    }
    document.addEventListener('keydown', handleShortcut)
    return () => document.removeEventListener('keydown', handleShortcut)
  }, [])

  useEffect(() => {
    if (!projMenuOpen) return
    // Refetch each open so newly created/renamed projects show; keep the cached list visible meanwhile.
    api.projects.list().then(setProjects).catch(() => setProjects(prev => prev ?? []))
  }, [projMenuOpen])

  useDismiss(projMenuOpen, projMenuRef, setProjMenuOpen)
  useDismiss(acctMenuOpen, acctMenuRef, setAcctMenuOpen)

  useEffect(() => {
    localStorage.setItem(NAV_KEY, JSON.stringify({ view: mainView, project }))
  }, [mainView, project])

  useEffect(() => {
    // A restored project that has since been deleted would leave every reload broken.
    if (project) api.projects.get(project.id).catch(() => setProject(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const closeMenu = () => setMobileMenuOpen(false)

  const navigate = (
    view: MainView,
    options?: { planningTab?: PlanningTabKey; focusEntityId?: string },
  ) => {
    if (view === 'planning') {
      setPlanningTab(options?.planningTab ?? 'phases')
      setPlanningFocus(options?.focusEntityId)
    }
    setMainView(view)
    setSearchQuery('')
    setSearchOpen(false)
    if (mobileNavMode) menuBtnRef.current?.focus()
    closeMenu()
  }

  // `open` = came from a Dashboard card, where the click means "take me into it".
  // Switching via the sidebar selector keeps you on whatever view you were reading.
  const selectProject = (p: SelectedProject, opts?: { open?: boolean }) => {
    setProject(p)
    if (opts?.open) setMainView('cockpit')
    if (mobileNavMode) menuBtnRef.current?.focus()
    closeMenu()
  }

  const openNotification = async (item: NotificationItem) => {
    if (project?.id !== item.project_id) {
      const target = await api.projects.get(item.project_id)
      setProject({ id: target.id, title: target.title, slug: target.slug })
    }
    const { view, ...options } = notificationTarget(item)
    navigate(view, options)
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
  const groups = useMemo(() => navGroups(Boolean(me)), [me])
  const searchableItems = useMemo(
    () => groups.flatMap(g => g.items.map(item => ({ ...item, group: g.group }))),
    [groups],
  )
  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return []
    return searchableItems.filter(item =>
      `${item.label} ${item.group} ${TITLES[item.view].sub}`.toLowerCase().includes(query),
    ).slice(0, 6)
  }, [searchQuery, searchableItems])

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setSearchQuery('')
      setSearchOpen(false)
      event.currentTarget.blur()
    } else if (event.key === 'Enter' && searchResults[0]) {
      event.preventDefault()
      navigate(searchResults[0].view)
    }
  }

  return (
    <div className="ab-app">
      {mobileMenuOpen && (
        <div className="ab-menu-overlay" aria-hidden="true" onClick={() => {
          closeMenu()
          menuBtnRef.current?.focus()
        }} />
      )}
      <aside
        ref={sidebarRef}
        id="ab-sidebar"
        className={`ab-sidebar${mobileMenuOpen ? ' ab-sidebar--open' : ''}`}
        aria-hidden={mobileNavMode && !mobileMenuOpen ? true : undefined}
      >
        <div className="ab-brand">
          <img className="ab-brand-mark" src="/planarus-icon.png" alt="" aria-hidden="true" />
          <div>
            <div className="ab-brand-name">Planarus</div>
            <div className="ab-brand-env">local · :{window.location.port || '80'}<LanAddress /></div>
          </div>
        </div>

        {/* Pinned above the scroll container: the selector stays put as the nav
            scrolls, and its menu is no longer clipped by that container's overflow. */}
        <div className="ab-side-pin">
          <div className="ab-projsel-wrap" ref={projMenuRef}>
            <button
              className="ab-projsel"
              type="button"
              aria-haspopup="listbox"
              aria-expanded={projMenuOpen}
              aria-label="Switch project"
              onClick={() => setProjMenuOpen(v => !v)}
            >
              <span className="pj-mark">{project ? initials(project.title) : MARK}</span>
              <span className="pj-meta">
                <span className="pj-name">{project ? project.title : 'All projects'}</span>
                <span className="pj-sub">{project ? project.slug : 'Select a project'}</span>
              </span>
              <Icon name="chevron-down" className="ic-14" />
            </button>
            {projMenuOpen && (
              <div className="ab-projsel-menu" role="listbox">
                <button
                  type="button"
                  className="ab-projsel-item"
                  role="option"
                  aria-selected={!project}
                  onClick={() => { setProject(null); setProjMenuOpen(false); navigate('dashboard') }}
                >
                  All projects
                </button>
                {projects === null ? (
                  <div className="ab-projsel-empty">Loading…</div>
                ) : projects.length === 0 ? (
                  <div className="ab-projsel-empty">No projects yet</div>
                ) : projects.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    className="ab-projsel-item"
                    role="option"
                    aria-selected={project?.id === p.id}
                    onClick={() => { selectProject({ id: p.id, title: p.title, slug: p.slug }); setProjMenuOpen(false) }}
                  >
                    <span className="pj-name">{p.title}</span>
                    <span className="pj-sub">{p.slug}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="ab-side-scroll">
          {groups.filter(g => g.group !== 'System').map((grp) => (
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

          {project && <SidebarTodos projectId={project.id} />}
        </div>

        <div className="ab-side-foot">
          {/* P11.3 account chip → now the trigger for the account menu: workspace-level
              destinations (Settings, Team) live here instead of a nav group. */}
          <div className="ab-projsel-wrap" ref={acctMenuRef}>
            <button
              className="ab-projsel"
              type="button"
              aria-haspopup="true"
              aria-expanded={acctMenuOpen}
              aria-label="Account and workspace settings"
              onClick={() => setAcctMenuOpen(v => !v)}
            >
              <span className="pj-mark">{me ? initials(me.user.display_name || me.user.email) : MARK}</span>
              <span className="pj-meta">
                <span className="pj-name">{me ? me.user.display_name : 'Local workspace'}</span>
                <span className="pj-sub">{me ? me.user.email : 'Single-user'}</span>
              </span>
              <Icon name="chevron-down" className="ic-14" />
            </button>
            {acctMenuOpen && (
              <div className="ab-projsel-menu ab-acct-menu">
                <div className="ab-projsel-empty">
                  {me ? (
                    `Signed in · ${me.memberships[0]?.role ?? 'member'}`
                  ) : (
                    <><span className="live-dot" title="Connected" /> Local mode · no sign-in</>
                  )}
                </div>
                {ACCOUNT_MENU.filter(it => it.view !== 'team' || me).map(it => (
                  <button
                    key={it.view}
                    type="button"
                    className="ab-projsel-item ab-acct-item"
                    onClick={() => { setAcctMenuOpen(false); navigate(it.view) }}
                  >
                    <Icon name={it.icon} className="ic-14" />
                    <span>{it.label}</span>
                  </button>
                ))}
                {/* A modal, not a view: About has no project scope and nothing
                    to restore on reload, so it stays out of the nav state. */}
                <button
                  type="button"
                  className="ab-projsel-item ab-acct-item"
                  onClick={() => { setAcctMenuOpen(false); setAboutOpen(true) }}
                >
                  <Icon name="info" className="ic-14" />
                  <span>About</span>
                </button>
                {me && (
                  <button
                    type="button"
                    className="ab-projsel-item ab-acct-item"
                    onClick={() => { setAcctMenuOpen(false); signOut() }}
                  >
                    <Icon name="external" className="ic-14" />
                    <span>Sign out</span>
                  </button>
                )}
              </div>
            )}
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
          <div className="ab-search-wrap">
            <label className="ab-search">
              <Icon name="search" className="ic-14" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                placeholder="Go to a view…"
                aria-label="Quick navigation"
                aria-expanded={searchOpen && Boolean(searchQuery.trim())}
                aria-controls="ab-search-results"
                autoComplete="off"
                onFocus={() => setSearchOpen(true)}
                onBlur={event => {
                  const wrap = event.currentTarget.closest('.ab-search-wrap')
                  if (!wrap?.contains(event.relatedTarget as Node | null)) setSearchOpen(false)
                }}
                onChange={event => { setSearchQuery(event.target.value); setSearchOpen(true) }}
                onKeyDown={handleSearchKeyDown}
              />
              <kbd>{typeof navigator !== 'undefined' && /Mac/.test(navigator.userAgent) ? '⌘K' : 'Ctrl K'}</kbd>
            </label>
            {searchOpen && searchQuery.trim() && (
              <div className="ab-search-results" id="ab-search-results" aria-label="Quick navigation results">
                {searchResults.length === 0 ? (
                  <div className="ab-search-empty">No matching view</div>
                ) : searchResults.map(result => (
                  <button key={result.view} type="button" onClick={() => navigate(result.view)}>
                    <span>{result.label}</span>
                    <small>{result.group}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
          <NotificationsBell projectId={project?.id ?? null} onOpenItem={item => void openNotification(item)} />
          <button className="ab-iconbtn" type="button" onClick={toggleTheme} aria-label="Toggle theme">
            <Icon name={isDark ? 'sun' : 'moon'} className="ic-18" />
          </button>
        </header>

        <main className="ab-content">
          <div className="ab-content-inner">
            <div style={{ minWidth: 0 }}>
              {mainView === 'dashboard' && <Dashboard onSelectProject={p => selectProject(p, { open: true })} />}
              {mainView === 'cockpit' && (project ? (
                <CockpitPanel
                  projectId={project.id}
                  onClose={() => setMainView('dashboard')}
                  onOpenCanvas={() => setMainView('canvas')}
                  // Same handler the bell uses, so a row about another project
                  // switches project before navigating (#95).
                  onOpenItem={item => void openNotification(item)}
                  onOpenApprovals={() => navigate('approvals')}
                  onOpenTasks={() => navigate('planning', { planningTab: 'tasks' })}
                  onOpenPlanning={tab => navigate('planning', { planningTab: tab })}
                />
              ) : placeholder)}
              {mainView === 'planning' && (project ? <PlanningPanel projectId={project.id} initialTab={planningTab} focusEntityId={planningFocus} /> : placeholder)}
              {mainView === 'roadmap' && (project ? <RoadmapPanel projectId={project.id} onOpenPlanning={() => navigate('planning', { planningTab: 'tasks' })} /> : placeholder)}
              {mainView === 'timeline' && (project ? <TimelinePanel projectId={project.id} /> : placeholder)}
              {mainView === 'calendar' && (project ? <CalendarPanel projectId={project.id} onOpenPlanning={() => navigate('planning', { planningTab: 'tasks' })} /> : placeholder)}
              {mainView === 'docs' && (project ? <DocsPanel projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'notes' && (project ? <DocsPanel key="notes" projectId={project.id} docType="note" onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'canvas' && (project ? <CanvasPanel projectId={project.id} onBack={() => setMainView('cockpit')} /> : placeholder)}
              {mainView === 'context-pack' && (project ? <ContextPackBuilder projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'context-files' && (project ? <ContextFilesPanel projectId={project.id} /> : placeholder)}
              {mainView === 'preview' && (project ? <MarkdownPreviewPanel projectId={project.id} /> : placeholder)}
              {mainView === 'approvals' && (project ? <ApprovalQueuePanel projectId={project.id} onClose={() => setMainView('dashboard')} /> : placeholder)}
              {mainView === 'agent-runs' && (project ? <AgentRunsPanel projectId={project.id} /> : placeholder)}
              {mainView === 'reminders' && (project ? <RemindersPanel projectId={project.id} /> : placeholder)}
              {mainView === 'team' && <TeamPanel />}
              {mainView === 'settings' && <SettingsPanel />}
            </div>
          </div>
        </main>
      </div>

      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} />}
    </div>
  )
}
