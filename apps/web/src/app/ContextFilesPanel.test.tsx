import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
})
