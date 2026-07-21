import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// forma design system — order matters: fonts + tokens before components.
import './styles/forma/fonts.css'
import './styles/forma/tokens.css'
import './styles/forma/themes.css'
import './styles/forma/components.css'
import './styles/forma/animations.css'
import './styles/planarus.css'
import './styles/index.css'
import App from './App'

// Default theme (the topbar toggles light-cosmo <-> dark-cosmo at runtime).
if (!document.documentElement.getAttribute('data-theme')) {
  document.documentElement.setAttribute('data-theme', 'light-cosmo')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
