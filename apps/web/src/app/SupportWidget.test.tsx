import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import SupportWidget from './SupportWidget'

afterEach(cleanup)

describe('SupportWidget', () => {
  it('reveals the author links and locks the thread after the first message', () => {
    render(<SupportWidget />)
    fireEvent.click(screen.getByRole('button', { name: 'Open support chat' }))
    expect(screen.getByText(/landing soon/)).toBeTruthy()

    const input = screen.getByLabelText('Message support') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'hello?' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(screen.getByText('hello?')).toBeTruthy()
    expect(screen.getByRole('link', { name: /LinkedIn/ })).toBeTruthy()
    expect((screen.getByRole('link', { name: /GitHub/ }) as HTMLAnchorElement).href).toContain('github.com/Sdomit')
    expect(screen.getByRole('link', { name: /Website/ })).toBeTruthy()
    // Thread is locked: input disabled and no further sends possible.
    expect(input.disabled).toBe(true)
  })
})
