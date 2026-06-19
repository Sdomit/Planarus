import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('renders the three-panel layout shell', () => {
    render(<App />)
    expect(screen.getByText('AgentBoard')).toBeTruthy()
    expect(screen.getByText('Dashboard')).toBeTruthy()
    expect(screen.getByText('AI Context')).toBeTruthy()
  })
})
