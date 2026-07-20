import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import Layout from './Layout'

// Every panel Layout renders hits the API on mount — stub the surfaces the
// default (dashboard) view and the two sidebar menus actually touch.
vi.mock('../api/client', () => {
  const never = () => new Promise(() => {}) // panels we don't assert on just stay loading
  return {
    api: {
      projects: {
        list: () => Promise.resolve([{ id: 'p1', title: 'Approvo', slug: 'approvo' }, { id: 'p2', title: 'Other', slug: 'other' }]),
        get: (id: string) => id === 'gone' ? Promise.reject(new Error('404')) : Promise.resolve({ id, title: 'Approvo', slug: 'approvo' }),
      },
      workspaces: { list: () => Promise.resolve([]) },
      approvals: { list: never },
      tasks: { list: never },
      risks: { list: never },
      settings: { get: never },
      todos: { list: never },
      notifications: { feed: () => Promise.resolve({ items: [] }) },
    },
  }
})

const me = {
  user: { id: 'u1', email: 'pat@team.lan', display_name: 'Pat', is_active: true, created_at: 't', updated_at: 't' },
  memberships: [{ workspace_id: 'ws1', role: 'owner' }],
}
let auth: { me: typeof me | null; signOut: () => void } = { me: null, signOut: vi.fn() }
vi.mock('./auth', () => ({ useAuthInfo: () => auth }))

beforeEach(() => { auth = { me: null, signOut: vi.fn() }; localStorage.clear() })
afterEach(cleanup)

const NAV_KEY = 'approvo.nav'

const openAccountMenu = () =>
  fireEvent.click(screen.getByLabelText('Account and workspace settings'))

describe('sidebar account menu', () => {
  it('opens from the workspace chip and navigates to Settings', () => {
    render(<Layout />)
    // Settings left the nav — it is only reachable through the account menu now.
    expect(screen.queryByText('Settings')).toBeNull()
    openAccountMenu()
    expect(screen.getByText('Local mode · no sign-in')).toBeTruthy()
    fireEvent.click(screen.getByText('Settings'))
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeTruthy()
  })

  it('shows Team + Sign out only in team mode', () => {
    render(<Layout />)
    openAccountMenu()
    expect(screen.queryByText('Sign out')).toBeNull()
    expect(screen.queryByText('Team')).toBeNull()
    cleanup()

    auth = { me, signOut: vi.fn() }
    render(<Layout />)
    openAccountMenu()
    expect(screen.getByText('Signed in · owner')).toBeTruthy()
    expect(screen.getByText('Team')).toBeTruthy()
    fireEvent.click(screen.getByText('Sign out'))
    expect(auth.signOut).toHaveBeenCalled()
  })

  it('closes on Escape', () => {
    render(<Layout />)
    openAccountMenu()
    expect(screen.getByText('Settings')).toBeTruthy()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('Settings')).toBeNull()
  })
})

describe('navigation state survives a reload', () => {
  const stored = () => JSON.parse(localStorage.getItem(NAV_KEY) ?? '{}')

  it('restores the open view and project on remount', () => {
    render(<Layout />)
    openAccountMenu()
    fireEvent.click(screen.getByText('Settings'))
    expect(stored().view).toBe('settings')

    cleanup() // stand-in for a browser refresh
    render(<Layout />)
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeTruthy()
  })

  it('drops a restored project the server no longer has', async () => {
    localStorage.setItem(NAV_KEY, JSON.stringify({ view: 'dashboard', project: { id: 'gone', title: 'Gone', slug: 'gone' } }))
    render(<Layout />)
    expect(screen.getByText('Gone')).toBeTruthy()
    await screen.findByText('All projects') // the selector falls back once the 404 lands
    expect(stored().project).toBeNull()
  })

  it('falls back to the dashboard when the stored view no longer exists', () => {
    localStorage.setItem(NAV_KEY, JSON.stringify({ view: 'view-deleted-in-a-later-release' }))
    render(<Layout />)
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeTruthy()
  })

  it('keeps the current view when the project is switched from the sidebar', async () => {
    render(<Layout />)
    openAccountMenu()
    fireEvent.click(screen.getByText('Settings'))

    fireEvent.click(screen.getByLabelText('Switch project'))
    fireEvent.click(await screen.findByText('Other'))

    // Still on Settings — switching projects must not bounce you to the Cockpit.
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeTruthy()
    expect(stored().project.id).toBe('p2')
  })
})
