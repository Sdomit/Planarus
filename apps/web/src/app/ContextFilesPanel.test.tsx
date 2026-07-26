import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import ContextFilesPanel from './ContextFilesPanel'

const file = {
  id: 'ctx_1',
  project_id: 'proj_1',
  kind: 'next_step',
  relative_path: 'context/NEXT_STEP.md',
  checksum: 'abc',
  generated_at: '2026-06-19T01:00:00+00:00',
  pinned: false,
  last_manual_edit_at: null,
  token_estimate: 42,
  created_at: 't',
  updated_at: 't',
}

vi.mock('../api/client', () => ({
  api: {
    projects: {
      get: vi.fn(async () => ({ id: 'proj_1', title: 'Demo', slug: 'demo', folder_path: '/srv/demo' })),
    },
    contextFiles: {
      list: vi.fn(async () => [file]),
      regenerate: vi.fn(async () => ({ project_id: 'proj_1', generated_at: 't', written: 0, drifted: 0, outcomes: [] })),
      setPinned: vi.fn(async (_id: string, pinned: boolean) => ({ ...file, pinned })),
      adopt: vi.fn(async () => ({
        ...file, checksum: 'adopted', pinned: true, last_manual_edit_at: 't',
      })),
    },
  },
}))

describe('ContextFilesPanel', () => {
  it('lists generated context files with a Regenerate action', async () => {
    render(<ContextFilesPanel projectId="proj_1" />)
    expect(await screen.findByText('NEXT_STEP.md')).toBeTruthy()
    expect(screen.getByText('Regenerate')).toBeTruthy()
    expect(screen.getByText('Demo')).toBeTruthy()
  })

  it('toggles the pin state', async () => {
    render(<ContextFilesPanel projectId="proj_1" />)
    const pinBtn = await screen.findByText('Pin')
    fireEvent.click(pinBtn)
    await waitFor(() => expect(screen.getByText('📌 Pinned')).toBeTruthy())
  })

  // #98: without a way to accept the on-disk copy, a hand edit dropped the file
  // out of every context pack for good.
  it('accepts the on-disk content, which pins the file', async () => {
    // Scoped to this render's container: the suite has no RTL auto-cleanup, so
    // earlier renders are still mounted and a bare screen query matches all of
    // them. The existing tests get away with it only because clicking Pin changes
    // the label they search for.
    const { container } = render(<ContextFilesPanel projectId="proj_1" />)
    const view = within(container)
    fireEvent.click(await view.findByText('Accept on-disk'))
    await waitFor(() => expect(view.getByText('📌 Pinned')).toBeTruthy())
    expect(view.getByText('hand-edited')).toBeTruthy()
  })
})
