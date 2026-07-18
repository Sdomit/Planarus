import Layout from './app/Layout'
import { AuthGate } from './app/auth'

export default function App() {
  return (
    <AuthGate>
      <Layout />
    </AuthGate>
  )
}
