import { useState } from 'react'
import '../styles/layout.css'
import Dashboard from './Dashboard'
import ContextFilesPanel from './ContextFilesPanel'
import PlanningPanel from './PlanningPanel'
import DocsPanel from './DocsPanel'
import ContextPackBuilder from './ContextPackBuilder'
import ApprovalQueuePanel from './ApprovalQueuePanel'
import ExternalClientsPanel from './ExternalClientsPanel'

type MainView = 'dashboard' | 'docs' | 'context-pack' | 'approvals' | 'clients'

// Minimal project context: Dashboard surfaces the selected project id so Layout
// can pass it to the Docs and Context Pack views.
const DEFAULT_PROJECT_ID = ''

const VIEW_TITLES: Record<MainView, string> = {
  dashboard: 'Dashboard',
  docs: 'Docs',
  'context-pack': 'Context Pack',
  approvals: 'Approval Queue',
  clients: 'External API Clients',
}

export default function Layout() {
  const [mainView, setMainView] = useState<MainView>('dashboard')
  const [projectId, setProjectId] = useState<string>(DEFAULT_PROJECT_ID)

  const handleOpenDocs = (id: string) => {
    setProjectId(id)
    setMainView('docs')
  }

  const handleOpenContextPack = (id: string) => {
    setProjectId(id)
    setMainView('context-pack')
  }

  const handleOpenApprovals = (id: string) => {
    setProjectId(id)
    setMainView('approvals')
  }

  const navButton = (view: MainView, label: string) => (
    <button
      type="button"
      onClick={() => setMainView(view)}
      style={{
        fontWeight: mainView === view ? 600 : 400,
        textDecoration: mainView === view ? 'underline' : 'none',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: '0.85rem',
      }}
    >
      {label}
    </button>
  )

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>AgentBoard</h1>
        </div>
        <div className="sidebar-planning">
          <PlanningPanel />
        </div>
      </aside>

      <main className="main">
        <div className="main-header">
          <h2>{VIEW_TITLES[mainView]}</h2>
          <nav
            className="main-nav"
            style={{ marginTop: '0.5rem', display: 'flex', gap: '0.75rem' }}
          >
            {navButton('dashboard', 'Dashboard')}
            {navButton('docs', 'Docs')}
            {navButton('context-pack', 'Context Pack')}
            {navButton('approvals', 'Approvals')}
            {navButton('clients', 'External API')}
          </nav>
        </div>
        <div className="main-content">
          {mainView === 'dashboard' && (
            <Dashboard
              onOpenDocs={handleOpenDocs}
              onOpenContextPack={handleOpenContextPack}
              onOpenApprovals={handleOpenApprovals}
            />
          )}
          {mainView === 'docs' &&
            (projectId ? (
              <DocsPanel projectId={projectId} onClose={() => setMainView('dashboard')} />
            ) : (
              <p style={{ color: '#888', fontSize: '0.85rem' }}>
                Select a project from the Dashboard first.
              </p>
            ))}
          {mainView === 'context-pack' &&
            (projectId ? (
              <ContextPackBuilder
                projectId={projectId}
                onClose={() => setMainView('dashboard')}
              />
            ) : (
              <p style={{ color: '#888', fontSize: '0.85rem' }}>
                Select a project from the Dashboard first.
              </p>
            ))}
          {mainView === 'approvals' &&
            (projectId ? (
              <ApprovalQueuePanel
                projectId={projectId}
                onClose={() => setMainView('dashboard')}
              />
            ) : (
              <p style={{ color: '#888', fontSize: '0.85rem' }}>
                Select a project from the Dashboard first.
              </p>
            ))}
          {/* External API client management is workspace-level (its own selectors),
              so it does not require a Dashboard project selection. */}
          {mainView === 'clients' && (
            <ExternalClientsPanel onClose={() => setMainView('dashboard')} />
          )}
        </div>
      </main>

      <aside className="context-panel">
        <div className="context-panel-header">
          <h2>AI Context</h2>
        </div>
        <div className="context-panel-content">
          <ContextFilesPanel />
        </div>
      </aside>
    </div>
  )
}
