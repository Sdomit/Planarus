import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import RecipesCard from './RecipesCard'

afterEach(cleanup)

describe('RecipesCard', () => {
  it('shows a copyable GitHub Actions workflow that uses a secret key', () => {
    render(<RecipesCard />)
    expect(screen.getByText(/name: approvo-status/)).toBeTruthy()
    expect(screen.getByText(/secrets\.APPROVO_API_KEY/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Copy workflow' })).toBeTruthy()
  })
})
