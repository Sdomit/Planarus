import { useState } from 'react'
import '../styles/layout.css'
import Dashboard from './Dashboard'
import ContextFilesPanel from './ContextFilesPanel'
import PlanningPanel from './PlanningPanel'
import DocsPanel from './DocsPanel'

type MainView = 'dashboard' | 'docs'

// Minimal project context: Dashboard surfaces the selected project id via
// a custom event so Layout can pass it to DocsPanel.
const DEFAULT_PROJECT_ID = ''

export default function Layout() {
  const [mainView, setMainView] = useState<MainView>('dashboard')
  const [docsProjectId, setDocsProjectId] = useState<string>(DEFAULT_PROJECT_ID)

  const handleOpenDocs = (projectId: string) => {
    setDocsProjectId(projectId)
    setMainView('docs')
  }

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
          {mainView === 'dashboard' ? (
            <h2>Dashboard</h2>
          ) : (
            <h2>Docs</h2>
          )}
          <nav className="main-nav" style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setMainView('dashboard')}
              style={{
                fontWeight: mainView === 'dashboard' ? 600 : 400,
                textDecoration: mainView === 'dashboard' ? 'underline' : 'none',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.85rem',
              }}
            >
              Dashboard
            </button>
            <button
              type="button"
              onClick={() => setMainView('docs')}
              style={{
                fontWeight: mainView === 'docs' ? 600 : 400,
                textDecoration: mainView === 'docs' ? 'underline' : 'none',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.85rem',
              }}
            >
              Docs
            </button>
          </nav>
        </div>
        <div className="main-content">
          {mainView === 'dashboard' && (
            <Dashboard onOpenDocs={handleOpenDocs} />
          )}
          {mainView === 'docs' && docsProjectId && (
            <DocsPanel
              projectId={docsProjectId}
              onClose={() => setMainView('dashboard')}
            />
          )}
          {mainView === 'docs' && !docsProjectId && (
            <p style={{ color: '#888', fontSize: '0.85rem' }}>
              Select a project from the Dashboard first.
            </p>
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
