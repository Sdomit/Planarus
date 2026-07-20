import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Icon } from './Icon'

// Guards the unsized-svg bug: an undefined size class (ic-16) left the svg with
// no width/height, so it rendered at the browser default 300x150.
describe('Icon', () => {
  it('always keeps the ic base class so an unknown size class still gets a size', () => {
    const { container } = render(<Icon name="palette" className="ic-99" />)
    const svg = container.querySelector('svg')!
    expect(svg.classList.contains('ic')).toBe(true)
    expect(svg.classList.contains('ic-99')).toBe(true)
  })

  it('defaults to the ic base class and renders the matching lucide icon', () => {
    const { container } = render(<Icon name="palette" />)
    const svg = container.querySelector('svg')!
    expect(svg.classList.contains('ic')).toBe(true)
    expect(svg.querySelector('path')).not.toBeNull()
  })

  it('renders nothing for an unknown icon name', () => {
    const { container } = render(<Icon name="not-a-real-icon" />)
    expect(container.querySelector('svg')).toBeNull()
  })
})
