import { BrowserRouter, Route, Routes } from 'react-router'
import Layout from './app/Layout'
import ProjectRoute from './app/ProjectRoute'
import { AuthGate } from './app/auth'

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          {/* #183 step 1: one project-scoped route (D63's workspace-qualified
              shape). Every other path — including a bare `/` and anything not
              yet migrated — keeps rendering Layout exactly as before it. */}
          <Route path="/w/:workspaceSlug/p/:projectSlug" element={<ProjectRoute />} />
          <Route path="/*" element={<Layout />} />
        </Routes>
      </BrowserRouter>
    </AuthGate>
  )
}
