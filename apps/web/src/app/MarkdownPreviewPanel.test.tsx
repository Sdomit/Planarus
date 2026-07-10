import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import MarkdownPreviewPanel from './MarkdownPreviewPanel'

afterEach(cleanup)

vi.mock('../api/client', () => ({
  api: {
    contextFiles: {
      list: vi.fn(async () => [
        {
          id: 'ctx_1',
          project_id: 'proj_1',
          kind: 'next_step',
          relative_path: 'context/NEXT_STEP.md',
          checksum: 'abc',
          generated_at: 't',
          pinned: false,
          last_manual_edit_at: null,
          token_estimate: 42,
          created_at: 't',
          updated_at: 't',
        },
      ]),
      content: vi.fn(async () => ({
        relative_path: 'context/NEXT_STEP.md',
        content: '# Current objective\n\nDo the **next** thing.',
        drifted: true,
      })),
    },
    docs: {
      list: vi.fn(async () => [
        {
          id: 'doc_1', project_id: 'proj_1', parent_doc_id: null, title: 'Spec',
          slug: 'spec', doc_type: 'spec', status: 'draft', sort_order: 0,
          version: 1, updated_at: 't', archived_at: null,
        },
      ]),
      get: vi.fn(async () => ({ markdown_cache: '# Spec doc' })),
    },
  },
}))

describe('MarkdownPreviewPanel', () => {
  it('lists context files and docs as sources', async () => {
    render(<MarkdownPreviewPanel projectId="proj_1" />)
    expect(await screen.findByText('context/NEXT_STEP.md')).toBeTruthy()
    expect(screen.getByText('doc: Spec')).toBeTruthy()
  })

  it('renders the selected context file with a drift warning', async () => {
    render(<MarkdownPreviewPanel projectId="proj_1" />)
    const select = await screen.findByLabelText('Source')
    fireEvent.change(select, { target: { value: 'context:ctx_1' } })
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Current objective'),
    )
    expect(screen.getByText('next')).toBeTruthy() // rendered <strong>, not literal **
    expect(screen.getByText(/edited on disk/)).toBeTruthy()
  })
})
