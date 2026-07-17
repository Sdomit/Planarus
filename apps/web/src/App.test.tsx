import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import App from './App'

// CanvasEditor pulls in Excalidraw, which can't evaluate under jsdom (no canvas).
vi.mock('./app/CanvasEditor', () => ({ CanvasEditor: () => null }))

afterEach(cleanup)

describe('App', () => {
  it('renders the forma app shell', () => {
    render(<App />)
    expect(screen.getByText('Approvo')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeTruthy()
    expect(screen.getByText('Planning')).toBeTruthy()
  })

  it('uses the topbar search as quick navigation', () => {
    render(<App />)
    const search = screen.getByLabelText('Quick navigation')
    fireEvent.change(search, { target: { value: 'roadmap' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(screen.getByRole('heading', { name: 'Roadmap' })).toBeTruthy()
  })
})
