import { BrowserRouter, Route, Routes } from 'react-router'
import Layout from './app/Layout'
import ProjectRoute from './app/ProjectRoute'
import { AuthGate } from './app/auth'

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          {/* #183 step 2: dashboard, settings and team are their own routes but
              stay uncontrolled (seeded once via initialView, NAV_KEY-backed) —
              they aren't project-scoped, so there's no URL to keep in sync as
              you navigate around from them (that's the 14 routes below). */}
          <Route path="/settings" element={<Layout initialView="settings" />} />
          <Route path="/team" element={<Layout initialView="team" />} />
          {/* The 14 project-scoped views (D63's workspace-qualified shape).
              Bare project route = cockpit (the project home); the :view
              segment covers the rest. Both resolve through the same
              ProjectRoute, which also owns the routed<->URL wiring. */}
          <Route path="/w/:workspaceSlug/p/:projectSlug" element={<ProjectRoute />} />
          <Route path="/w/:workspaceSlug/p/:projectSlug/:view" element={<ProjectRoute />} />
          {/* #183 step 3: nested detail routes, in order of value (approvals ->
              tasks -> docs). More specific than the :view route above, so
              React Router matches this first for a path with the extra
              segment. */}
          <Route
            path="/w/:workspaceSlug/p/:projectSlug/approvals/:approvalId"
            element={<ProjectRoute />}
          />
          <Route
            path="/w/:workspaceSlug/p/:projectSlug/planning/task/:taskId"
            element={<ProjectRoute />}
          />
          {/* Bare `/` (dashboard) and anything this migration hasn't reached
              yet keep rendering Layout exactly as it always has. */}
          <Route path="/*" element={<Layout />} />
        </Routes>
      </BrowserRouter>
    </AuthGate>
  )
}
