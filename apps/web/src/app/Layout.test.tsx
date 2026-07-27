import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import Layout, { notificationTarget } from './Layout'

// Every panel Layout renders hits the API on mount — stub the surfaces the
// default (dashboard) view and the two sidebar menus actually touch.
vi.mock('../api/client', () => {
  const never = () => new Promise(() => {}) // panels we don't assert on just stay loading
  return {
    api: {
      projects: {
        list: () => Promise.resolve([{ id: 'p1', title: 'Planarus', slug: 'planarus' }, { id: 'p2', title: 'Other', slug: 'other' }]),
        get: (id: string) => id === 'gone' ? Promise.reject(new Error('404')) : Promise.resolve({ id, title: 'Planarus', slug: 'planarus' }),
      },
      workspaces: { list: () => Promise.resolve([]) },
      approvals: { list: never },
      tasks: { list: never },
      risks: { list: never },
      settings: { get: never },
      todos: { list: never },
      notifications: { feed: () => Promise.resolve({ items: [] }) },
      info: { get: () => Promise.resolve({ name: 'Planarus', version: '0.1.0', phase: 'x', lan_ip: '192.168.1.42' }) },
    },
  }
})

const me = {
  user: { id: 'u1', email: 'pat@team.lan', display_name: 'Pat', is_active: true, created_at: 't', updated_at: 't' },
  memberships: [{ workspace_id: 'ws1', role: 'owner' }],
}
let auth: { me: typeof me | null; signOut: () => void } = { me: null, signOut: vi.fn() }
vi.mock('./auth', () => ({ useAuthInfo: () => auth }))

beforeEach(() => {
  auth = { me: null, signOut: vi.fn() }
  localStorage.clear()
  document.documentElement.setAttribute('data-theme', 'light-cosmo')
})
afterEach(cleanup)

const NAV_KEY = 'planarus.nav'

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

describe('about', () => {
  it('opens from the account menu with the live version and author links', async () => {
    render(<Layout />)
    openAccountMenu()
    fireEvent.click(screen.getByText('About'))

    const dialog = screen.getByRole('dialog', { name: 'About Planarus' })
    expect(await within(dialog).findByText('0.1.0')).toBeTruthy() // from the API, not a constant
    expect(within(dialog).getByText('Sarmad Domit')).toBeTruthy()
    expect(within(dialog).getByText('www.sarmaddomit.com').getAttribute('href'))
      .toBe('https://www.sarmaddomit.com')
    expect(within(dialog).getByText('sarmad.domit@gmail.com').getAttribute('href'))
      .toBe('mailto:sarmad.domit@gmail.com')

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'About Planarus' })).toBeNull()
  })
})

describe('LAN address', () => {
  it('copies this machine\'s URL, not the loopback one', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    Object.assign(navigator, { clipboard: { writeText } })
    render(<Layout />)

    fireEvent.click(await screen.findByText('ip'))
    expect(writeText).toHaveBeenCalledWith(`http://192.168.1.42:${window.location.port || '80'}`)
    expect(await screen.findByText('copied ✓')).toBeTruthy()
  })
})

describe('Cosmo theme', () => {
  it('renders the approved brand mark', () => {
    const { container } = render(<Layout />)

    expect(container.querySelector('.ab-brand-mark')?.getAttribute('src'))
      .toBe('/planarus-icon.png')
  })

  it('toggles the persisted Cosmo light and dark pair', () => {
    render(<Layout />)

    fireEvent.click(screen.getByLabelText('Toggle theme'))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark-cosmo')
    expect(localStorage.getItem('planarus.theme')).toBe('dark-cosmo')

    fireEvent.click(screen.getByLabelText('Toggle theme'))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light-cosmo')
    expect(localStorage.getItem('planarus.theme')).toBe('light-cosmo')
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
    // The fallback (DOM) and the persist-to-localStorage run in separate effects
    // with no ordering guarantee, so poll the stored value rather than assuming
    // it lands in the same tick as the text (React 19 widened that window).
    await waitFor(() => expect(stored().project).toBeNull())
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

describe('brand mark', () => {
  // The letter-mark rename guard that used to live here retired with the
  // letter: the mark is now the approved artwork, asserted in "Cosmo theme".

  it('falls back to the product initials in the chips, not a stale brand', () => {
    // Same rename miss, one layer down: the project selector and account chip
    // both hardcoded "AB" (AgentBoard). No project + local mode = both fall back.
    const { container } = render(<Layout />)
    const name = container.querySelector('.ab-brand-name')?.textContent?.trim() ?? ''
    const marks = Array.from(container.querySelectorAll('.pj-mark'), (e) => e.textContent?.trim())
    expect(marks.length).toBe(2)
    expect(marks).toEqual([name.slice(0, 2).toUpperCase(), name.slice(0, 2).toUpperCase()])
  })
})

describe('notificationTarget (#95)', () => {
  const item = (id: string, kind: string) => ({
    id, kind, severity: 'warn', title: 't', detail: null,
    project_id: 'p1', project_title: 'Planarus', at: '2026-07-26T00:00:00+00:00',
  })

  it('sends approval rows to the queue, with nothing to scroll to there', () => {
    expect(notificationTarget(item('approval_pending:apr_1', 'approval_pending')))
      .toEqual({ view: 'approvals' })
  })

  it('sends each planning row to the tab that actually holds it', () => {
    // The bug: all three of these landed on Tasks, and two of them do not live there.
    expect(notificationTarget(item('task_overdue:tsk_1', 'task_overdue')))
      .toEqual({ view: 'planning', planningTab: 'tasks', focusEntityId: 'tsk_1' })
    expect(notificationTarget(item('blocker_open:blk_1', 'blocker_open')))
      .toEqual({ view: 'planning', planningTab: 'risks', focusEntityId: 'blk_1' })
    expect(notificationTarget(item('milestone_missed:mls_1', 'milestone_missed')))
      .toEqual({ view: 'planning', planningTab: 'milestones', focusEntityId: 'mls_1' })
  })

  it('leaves the focus empty rather than guessing when the id carries no entity', () => {
    expect(notificationTarget(item('task_overdue:', 'task_overdue')).focusEntityId).toBeUndefined()
  })
})

describe('capture intake (#106)', () => {
  const NAV = { view: 'dashboard', project: { id: 'p1', title: 'Planarus', slug: 'planarus' } }

  function open(payload: unknown) {
    localStorage.setItem(NAV_KEY, JSON.stringify(NAV))
    window.location.hash = `#capture=${encodeURIComponent(JSON.stringify(payload))}`
    return render(<Layout />)
  }

  afterEach(() => { window.location.hash = '' })

  // Layout owns the routing decision and the fragment lifecycle; what each panel
  // then does with the clip is asserted in that panel's own tests, where the API
  // is mocked properly (this file's mock deliberately leaves panels loading).
  it('opens the surface the clip type belongs to', async () => {
    open({ type: 'risk', text: 'Vendor may miss the date', url: 'https://example.com/a' })
    // The type is picked in the native context menu (D66), so the app never asks.
    expect(await screen.findByRole('heading', { name: 'Planning' })).toBeTruthy()
  })

  it('sends a doc clip to Docs, not to Planning', async () => {
    open({ type: 'doc', text: 'Notes on the vendor call' })
    expect(await screen.findByRole('heading', { name: 'Docs' })).toBeTruthy()
  })

  it('strips the fragment so a refresh cannot file the same clip twice', async () => {
    open({ type: 'task', text: 'Ship the beta' })
    await screen.findByRole('heading', { name: 'Planning' })
    expect(window.location.hash).toBe('')
  })

  it('boots normally on a malformed fragment', async () => {
    localStorage.setItem(NAV_KEY, JSON.stringify(NAV))
    window.location.hash = '#capture=%7Bnot-json'
    render(<Layout />)
    // No crash, no navigation — the view the user left is what they get.
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy()
  })
})
