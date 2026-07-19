import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import RestApiCard from './RestApiCard'

afterEach(cleanup)

describe('RestApiCard', () => {
  it('surfaces the reachable external base URL, liveness endpoint, and a keyed snippet', () => {
    render(<RestApiCard active permitted />)
    // Only /api/* is proxied to the backend, so we surface the external base…
    expect(screen.getByText(/\/api\/external\/v1$/)).toBeTruthy()
    // …and the unauthenticated info endpoint for liveness/version checks.
    expect(screen.getByText(/\/api\/v1\/info$/)).toBeTruthy()
    // Default curl snippet carries the Bearer key placeholder.
    expect(screen.getByText(/Authorization: Bearer agbk_<key_id>_<secret>/)).toBeTruthy()
  })

  it('switches the snippet language', () => {
    render(<RestApiCard active permitted />)
    fireEvent.click(screen.getByRole('tab', { name: 'Python' }))
    expect(screen.getByText(/import requests/)).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: 'TypeScript' }))
    expect(screen.getByText(/await fetch/)).toBeTruthy()
  })

  it('reflects inert status when the API is not permitted by the environment', () => {
    render(<RestApiCard active={false} permitted={false} />)
    expect(screen.getByText(/not permitted by environment/i)).toBeTruthy()
  })

  it('copies the base URL to the clipboard', () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<RestApiCard active permitted />)
    // The base-URL row's Copy button is the first exact-"Copy" button.
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy' })[0])
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/api/external/v1'))
  })
})
