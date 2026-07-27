import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import FolderPicker from './FolderPicker'
import { api } from '../api/client'

// Phase 12d. The picker exists so nobody has to hand-type an absolute path, and
// the server hands back directory names only. What matters here: it navigates
// with real paths, it never invents one, and the local-mode-only refusal is
// shown rather than swallowed.

vi.mock('../api/client', () => ({ api: { fs: { dirs: vi.fn() } } }))

const listing = {
  path: '/home/dev',
  parent: '/home',
  is_git: false,
  roots: ['/', '/home/dev'],
  message: null,
  dirs: [
    { name: 'notes', path: '/home/dev/notes', is_git: false },
    { name: 'planarus', path: '/home/dev/planarus', is_git: true },
  ],
}

beforeEach(() => {
  vi.mocked(api.fs.dirs).mockReset().mockResolvedValue({ ...listing })
})

afterEach(cleanup)

describe('FolderPicker', () => {
  it('opens on the default folder and lists its subdirectories', async () => {
    render(<FolderPicker onSelect={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('planarus')).toBeTruthy())
    expect(screen.getByText('notes')).toBeTruthy()
    // No argument: the server decides the starting folder (the user's home).
    expect(api.fs.dirs).toHaveBeenCalledWith(undefined)
  })

  it('badges repo roots so the folder worth picking is obvious', async () => {
    render(<FolderPicker onSelect={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('planarus')).toBeTruthy())
    // One badge, on the one directory the server flagged as a repo.
    expect(screen.getAllByText('git')).toHaveLength(1)
  })

  it('navigates into a folder and back up by path', async () => {
    render(<FolderPicker onSelect={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByText('planarus'))
    await waitFor(() => expect(api.fs.dirs).toHaveBeenCalledWith('/home/dev/planarus'))
    fireEvent.click(screen.getByRole('button', { name: /up/i }))
    await waitFor(() => expect(api.fs.dirs).toHaveBeenCalledWith('/home'))
  })

  it('returns the folder currently open, not a subfolder', async () => {
    const onSelect = vi.fn()
    render(<FolderPicker onSelect={onSelect} onClose={vi.fn()} />)
    await screen.findByText('planarus')
    fireEvent.click(screen.getByRole('button', { name: /use this folder/i }))
    expect(onSelect).toHaveBeenCalledWith('/home/dev')
  })

  it('cannot go up from a filesystem root', async () => {
    vi.mocked(api.fs.dirs).mockResolvedValue({ ...listing, path: '/', parent: null })
    render(<FolderPicker onSelect={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /up/i }).hasAttribute('disabled')).toBe(true),
    )
  })

  it('shows the team-mode refusal instead of an empty list', async () => {
    vi.mocked(api.fs.dirs).mockRejectedValue(
      new Error('filesystem browsing is a local single-user surface and is disabled in team/hosted mode'),
    )
    render(<FolderPicker onSelect={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/disabled in team\/hosted mode/i)).toBeTruthy())
  })

  it('reports an unreadable folder without breaking navigation', async () => {
    vi.mocked(api.fs.dirs).mockResolvedValue({
      ...listing, dirs: [], message: 'Folder could not be read.',
    })
    render(<FolderPicker onSelect={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Folder could not be read.')).toBeTruthy())
    expect(screen.getByText(/no subfolders/i)).toBeTruthy()
  })
})
