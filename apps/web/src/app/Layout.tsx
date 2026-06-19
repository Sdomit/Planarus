import '../styles/layout.css'
import Dashboard from './Dashboard'
import ContextFilesPanel from './ContextFilesPanel'
import PlanningPanel from './PlanningPanel'

export default function Layout() {
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
          <h2>Dashboard</h2>
        </div>
        <div className="main-content">
          <Dashboard />
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
