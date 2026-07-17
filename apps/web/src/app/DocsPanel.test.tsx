import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll, afterAll } from 'vitest'
import { Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import { TaskList, TaskItem } from '@tiptap/extension-list'
import Image from '@tiptap/extension-image'
import { TextStyle } from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import DocsPanel, { serializeToMarkdown } from './DocsPanel'

// CanvasEditor pulls in Excalidraw, which can't evaluate under jsdom (no canvas).
// These tests don't exercise the canvas, so stub it out.
vi.mock('./CanvasEditor', () => ({ CanvasEditor: () => null }))

vi.mock('../api/client', () => ({
  api: {
    docs: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      exportMarkdown: vi.fn(),
    },
  },
}))

import { api } from '../api/client'

const mockApi = api as unknown as {
  docs: {
    list: ReturnType<typeof vi.fn>
    get: ReturnType<typeof vi.fn>
    create: ReturnType<typeof vi.fn>
    update: ReturnType<typeof vi.fn>
    exportMarkdown: ReturnType<typeof vi.fn>
  }
}

const DOC_SUMMARY = {
  id: 'doc_1',
  project_id: 'proj_1',
  parent_doc_id: null,
  title: 'Test Note',
  slug: 'test-note',
  doc_type: 'note',
  status: 'draft',
  sort_order: 0,
  version: 1,
  updated_at: '2026-06-20T00:00:00+00:00',
  archived_at: null,
}

const DOC_FULL = {
  ...DOC_SUMMARY,
  editor_format: 'tiptap_json',
  content_json: '{"type": "doc", "content": [{"type": "paragraph"}]}',
  markdown_cache: '',
  export_relative_path: null,
  export_checksum: null,
  exported_at: null,
  created_at: '2026-06-20T00:00:00+00:00',
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('DocsPanel', () => {
  it('renders "Loading docs…" while fetching', async () => {
    mockApi.docs.list.mockReturnValue(new Promise(() => {})) // never resolves
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    expect(screen.getByText(/Loading docs/i)).toBeTruthy()
  })

  it('shows empty state when no docs', async () => {
    mockApi.docs.list.mockResolvedValue([])
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/No docs yet/i)).toBeTruthy())
  })

  it('shows doc list when docs exist', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Test Note')).toBeTruthy())
  })

  it('shows "+ New Doc" button', async () => {
    mockApi.docs.list.mockResolvedValue([])
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('+ New Doc')).toBeTruthy())
  })

  it('clicking "+ New Doc" shows create form', async () => {
    mockApi.docs.list.mockResolvedValue([])
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('+ New Doc'))
    fireEvent.click(screen.getByText('+ New Doc'))
    expect(screen.getByPlaceholderText('Doc title')).toBeTruthy()
  })

  it('create form calls api.docs.create and navigates to editor on success', async () => {
    mockApi.docs.list.mockResolvedValue([])
    mockApi.docs.create.mockResolvedValue(DOC_FULL)
    mockApi.docs.get.mockResolvedValue(DOC_FULL)

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('+ New Doc'))
    fireEvent.click(screen.getByText('+ New Doc'))

    const titleInput = screen.getByPlaceholderText('Doc title')
    fireEvent.change(titleInput, { target: { value: 'New Doc' } })
    fireEvent.click(screen.getByText('Create'))

    await waitFor(() =>
      expect(mockApi.docs.create).toHaveBeenCalledWith('proj_1', {
        title: 'New Doc',
        doc_type: 'note',
      })
    )
  })

  it('clicking a doc item opens the editor view', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))

    await waitFor(() => expect(mockApi.docs.get).toHaveBeenCalledWith('doc_1'))
  })

  it('shows error if list fails', async () => {
    mockApi.docs.list.mockRejectedValue(new Error('network error'))
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/network error/i)).toBeTruthy())
  })

  it('calls onClose when ✕ is clicked', async () => {
    mockApi.docs.list.mockResolvedValue([])
    const onClose = vi.fn()
    render(<DocsPanel projectId="proj_1" onClose={onClose} />)
    await waitFor(() => screen.getByText('+ New Doc'))
    fireEvent.click(screen.getByTitle('Close docs'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('export success shows path message', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)
    mockApi.docs.exportMarkdown.mockResolvedValue({
      export_path: 'docs/my-note.md',
      was_changed: true,
      drift_detected: false,
      checksum: 'abc123',
    })

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))
    await waitFor(() => expect(mockApi.docs.get).toHaveBeenCalled())
    await waitFor(() => screen.getByText('Export Markdown'))

    fireEvent.click(screen.getByText('Export Markdown'))
    await waitFor(() => expect(screen.getByText(/Exported to docs\/my-note\.md/i)).toBeTruthy())
  })

  it('export drift 409 shows safe error message without force-retry', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)
    mockApi.docs.exportMarkdown.mockRejectedValue(
      new Error('409: {"detail":"The exported Markdown file was changed outside Approvo. Review it before exporting again."}'),
    )
    const confirmSpy = vi.spyOn(window, 'confirm')

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))
    await waitFor(() => expect(mockApi.docs.get).toHaveBeenCalled())
    await waitFor(() => screen.getByText('Export Markdown'))

    fireEvent.click(screen.getByText('Export Markdown'))
    await waitFor(() =>
      expect(screen.getByText(/changed outside Approvo/i)).toBeTruthy(),
    )
    // exportMarkdown called exactly once — no force-retry
    expect(mockApi.docs.exportMarkdown).toHaveBeenCalledTimes(1)
    // No confirm dialog was shown
    expect(confirmSpy).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// serializeToMarkdown — rich Markdown fidelity tests
// ---------------------------------------------------------------------------

describe('serializeToMarkdown', () => {
  let editor: Editor

  beforeAll(() => {
    const el = document.createElement('div')
    document.body.appendChild(el)
    editor = new Editor({
      element: el,
      extensions: [
        StarterKit.configure({ link: { openOnClick: false } }),
        TextStyle, Color, Highlight, Subscript, Superscript, TaskList, TaskItem, Image,
      ],
    })
  })

  afterAll(() => {
    editor.destroy()
  })

  it('serializes heading level 1', () => {
    act(() => { editor.commands.setContent('<h1>My Title</h1>') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('# My Title')
  })

  it('serializes heading level 2', () => {
    act(() => { editor.commands.setContent('<h2>Section</h2>') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('## Section')
  })

  it('serializes bold', () => {
    act(() => { editor.commands.setContent('<p><strong>bold text</strong></p>') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('**bold text**')
  })

  it('serializes italic', () => {
    act(() => { editor.commands.setContent('<p><em>italic text</em></p>') })
    expect(serializeToMarkdown(editor.state.doc)).toMatch(/\*italic text\*|_italic text_/)
  })

  it('serializes bullet list', () => {
    act(() => { editor.commands.setContent('<ul><li><p>Item A</p></li><li><p>Item B</p></li></ul>') })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('* Item A')
    expect(md).toContain('* Item B')
  })

  it('serializes ordered list', () => {
    act(() => { editor.commands.setContent('<ol><li><p>First</p></li><li><p>Second</p></li></ol>') })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('1. First')
    expect(md).toContain('2. Second')
  })

  it('serializes blockquote', () => {
    act(() => { editor.commands.setContent('<blockquote><p>A quote</p></blockquote>') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('> A quote')
  })

  it('serializes underline as inline HTML', () => {
    act(() => { editor.commands.setContent('<p><u>underlined</u></p>') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('<u>underlined</u>')
  })

  it('serializes highlight with == markers', () => {
    act(() => { editor.commands.setContent('<p><mark>marked</mark></p>') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('==marked==')
  })

  it('serializes subscript and superscript as inline HTML', () => {
    act(() => { editor.commands.setContent('<p>H<sub>2</sub>O and x<sup>2</sup></p>') })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('H<sub>2</sub>O')
    expect(md).toContain('x<sup>2</sup>')
  })

  it('serializes font color as an inline HTML span', () => {
    act(() => { editor.commands.setContent('<p><span style="color: #ff0000">red</span></p>') })
    expect(serializeToMarkdown(editor.state.doc)).toMatch(/<span style="color:[^"]+">red<\/span>/)
  })

  it('serializes image as Markdown', () => {
    act(() => { editor.commands.setContent('<img src="https://ex.com/a.png" alt="a pic">') })
    expect(serializeToMarkdown(editor.state.doc)).toContain('![a pic](https://ex.com/a.png)')
  })

  it('serializes task list as GFM checkboxes', () => {
    act(() => {
      editor.commands.setContent(
        '<ul data-type="taskList">' +
        '<li data-type="taskItem" data-checked="true"><p>done</p></li>' +
        '<li data-type="taskItem" data-checked="false"><p>todo</p></li>' +
        '</ul>',
      )
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('- [x] done')
    expect(md).toContain('- [ ] todo')
  })

  it('serializes code block with fence markers', () => {
    act(() => { editor.commands.setContent('<pre><code>const x = 1</code></pre>') })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('```')
    expect(md).toContain('const x = 1')
  })

  it('produces non-empty structured Markdown (not plain text) for mixed content', () => {
    act(() => {
      editor.commands.setContent(
        '<h1>Title</h1><p><strong>bold</strong> and <em>italic</em></p><ul><li><p>item</p></li></ul>',
      )
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('# Title')
    expect(md).toContain('**bold**')
    expect(md).toMatch(/\*italic\*|_italic_/)
    expect(md).toContain('* item')
  })
})
