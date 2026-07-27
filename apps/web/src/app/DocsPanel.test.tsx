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
import { Details, DetailsSummary, DetailsContent } from '@tiptap/extension-details'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import DocsPanel, { serializeToMarkdown, PlanarusMention, ChildPage, Callout } from './DocsPanel'

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
      remove: vi.fn(),
      exportMarkdown: vi.fn(),
      // P11.2 presence: reject like the auth-off backend so the hook goes dormant.
      presenceBeat: vi.fn().mockRejectedValue(new Error('404: not found')),
      presenceLeave: vi.fn().mockResolvedValue(undefined),
    },
    // #138: ReferencedBy's backlink lookup — empty by default so it renders nothing.
    mentions: {
      list: vi.fn().mockResolvedValue([]),
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
    remove: ReturnType<typeof vi.fn>
    exportMarkdown: ReturnType<typeof vi.fn>
    presenceBeat: ReturnType<typeof vi.fn>
    presenceLeave: ReturnType<typeof vi.fn>
  }
  mentions: {
    list: ReturnType<typeof vi.fn>
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

// jsdom ships no layout engine, so Range has neither getClientRects nor
// getBoundingClientRect — and ProseMirror asks a Range for both whenever a
// command scrolls the selection into view (arming Edit focuses the doc). Zero
// rects are enough: nothing here asserts on geometry.
beforeAll(() => {
  const proto = Range.prototype as unknown as Record<string, unknown>
  proto.getClientRects = () => []
  proto.getBoundingClientRect = () => ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 })
})

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
  // A fake-timer test that fails before its own useRealTimers() would otherwise
  // leave timers faked, hanging every test after it in 5s waitFor timeouts.
  vi.useRealTimers()
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

  it('docType="note" renders a card grid with the body excerpt; docs stay a list', async () => {
    mockApi.docs.list.mockResolvedValue([{ ...DOC_SUMMARY, excerpt: 'milk, eggs, bread' }])
    const { container, unmount } = render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Test Note')).toBeTruthy())
    expect(container.querySelector('.ab-notegrid')).toBeTruthy()
    expect(screen.getByText('milk, eggs, bread')).toBeTruthy()
    unmount()

    // The unlocked Docs view must keep the plain list — no grid regression.
    const docs = render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Test Note')).toBeTruthy())
    expect(docs.container.querySelector('.ab-notegrid')).toBeNull()
    expect(docs.container.querySelector('.ab-doclist')).toBeTruthy()
  })

  it('picking a swatch saves the colour and paints the card', async () => {
    mockApi.docs.list.mockResolvedValue([{ ...DOC_SUMMARY, color: null }])
    mockApi.docs.update.mockResolvedValue({ ...DOC_FULL, color: 'teal', version: 2 })
    const { container } = render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    expect(container.querySelector('.ab-notecard')?.getAttribute('data-color')).toBeNull()

    fireEvent.click(screen.getByLabelText('teal'))
    await waitFor(() =>
      expect(mockApi.docs.update).toHaveBeenCalledWith('doc_1', { color: 'teal', version: 1 })
    )
    // The card repaints from the response — and picks up the bumped version, so a
    // second pick doesn't 409.
    await waitFor(() =>
      expect(container.querySelector('.ab-notecard')?.getAttribute('data-color')).toBe('teal')
    )
    fireEvent.click(screen.getByLabelText('red'))
    await waitFor(() =>
      expect(mockApi.docs.update).toHaveBeenLastCalledWith('doc_1', { color: 'red', version: 2 })
    )
  })

  it('clearing a colour sends the "default" sentinel, and re-picking the same colour is a no-op', async () => {
    mockApi.docs.list.mockResolvedValue([{ ...DOC_SUMMARY, color: 'teal' }])
    mockApi.docs.update.mockResolvedValue({ ...DOC_FULL, color: null, version: 2 })
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))

    fireEvent.click(screen.getByLabelText('teal'))       // already teal
    expect(mockApi.docs.update).not.toHaveBeenCalled()

    fireEvent.click(screen.getByLabelText('No colour'))
    await waitFor(() =>
      expect(mockApi.docs.update).toHaveBeenCalledWith('doc_1', { color: 'default', version: 1 })
    )
  })

  it('a failed colour change refetches instead of showing a stale swatch', async () => {
    mockApi.docs.list.mockResolvedValue([{ ...DOC_SUMMARY, color: null }])
    mockApi.docs.update.mockRejectedValue(new Error('409: version conflict'))
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    expect(mockApi.docs.list).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByLabelText('blue'))
    await waitFor(() => expect(mockApi.docs.list).toHaveBeenCalledTimes(2))
  })

  it('colouring from inside the editor adopts the new version so the next save works', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)                     // version 1
    mockApi.docs.update.mockResolvedValue({ ...DOC_FULL, color: 'green', version: 2 })
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))
    await waitFor(() => screen.getByText('Export Markdown'))         // editor is open

    fireEvent.click(screen.getByLabelText('green'))
    await waitFor(() =>
      expect(mockApi.docs.update).toHaveBeenCalledWith('doc_1', { color: 'green', version: 1 })
    )

    // The editor must adopt the bumped version: a second change sends 2, not 1.
    // (This covers the `doc` state path. The versionRef that `save` itself reads
    // is set on the same line; dirtying ProseMirror under jsdom to click Save
    // isn't worth the scaffolding, so that path is checked in the browser.)
    mockApi.docs.update.mockResolvedValue({ ...DOC_FULL, color: null, version: 3 })
    fireEvent.click(screen.getByLabelText('No colour'))
    await waitFor(() =>
      expect(mockApi.docs.update).toHaveBeenLastCalledWith('doc_1', { color: 'default', version: 2 })
    )
  })

  it('the Docs list row carries the colour, and an uncoloured one has no attribute', async () => {
    mockApi.docs.list.mockResolvedValue([
      { ...DOC_SUMMARY, id: 'doc_1', title: 'Coloured', color: 'orange' },
      { ...DOC_SUMMARY, id: 'doc_2', title: 'Plain', color: null },
    ])
    const { container } = render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Coloured'))
    const rows = container.querySelectorAll('.ab-docitem')
    expect(rows[0].getAttribute('data-color')).toBe('orange')
    expect(rows[1].getAttribute('data-color')).toBeNull()
  })

  it('live search debounces and sends the raw query to the server', async () => {
    vi.useFakeTimers()
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(250) })
    mockApi.docs.list.mockClear()

    const box = screen.getByPlaceholderText('Search notes…')
    fireEvent.change(box, { target: { value: 'gro' } })
    fireEvent.change(box, { target: { value: 'groc' } })
    // Mid-debounce: still nothing sent.
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(mockApi.docs.list).not.toHaveBeenCalled()

    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    // One request for the settled value, not one per keystroke. Case is preserved —
    // the server lowercases both sides, so matching stays insensitive.
    expect(mockApi.docs.list).toHaveBeenCalledTimes(1)
    expect(mockApi.docs.list).toHaveBeenCalledWith('proj_1', { doc_type: 'note', q: 'groc' })
    vi.useRealTimers()
  })

  it('a search with no hits says so instead of showing the empty-state pitch', async () => {
    vi.useFakeTimers()
    mockApi.docs.list.mockResolvedValue([])
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(250) })
    fireEvent.change(screen.getByPlaceholderText('Search notes…'), { target: { value: 'zzz' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(250) })
    expect(screen.getByText(/No notes match/)).toBeTruthy()
    expect(screen.queryByText(/No notes yet/)).toBeNull()
    vi.useRealTimers()
  })

  it('deleting a note card asks first, then drops it from the grid', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.remove.mockResolvedValue(undefined)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))

    fireEvent.click(screen.getByLabelText('Delete Test Note'))
    expect(confirm).toHaveBeenCalled()
    expect(mockApi.docs.remove).not.toHaveBeenCalled()   // declined = no delete

    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByLabelText('Delete Test Note'))
    await waitFor(() => expect(mockApi.docs.remove).toHaveBeenCalledWith('doc_1'))
    await waitFor(() => expect(screen.queryByText('Test Note')).toBeNull())
    confirm.mockRestore()
  })

  it('renaming in the editor autosaves the title without blanking it on empty', async () => {
    vi.useFakeTimers()
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)
    mockApi.docs.update.mockResolvedValue({ ...DOC_FULL, title: 'Renamed', version: 2 })
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(250) })
    fireEvent.click(screen.getByText('Test Note'))
    await act(async () => { await vi.advanceTimersByTimeAsync(50) })

    const titleBox = screen.getByLabelText('Title') as HTMLInputElement
    expect(titleBox.value).toBe('Test Note')

    fireEvent.change(titleBox, { target: { value: 'Renamed' } })
    expect(mockApi.docs.update).not.toHaveBeenCalled()      // debounced, not per keystroke
    // No waitFor under fake timers — it polls on the very timers we froze.
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(mockApi.docs.update.mock.calls[0][1].title).toBe('Renamed')

    // Clearing the box must not save an empty title — blur restores the current one.
    mockApi.docs.update.mockClear()
    fireEvent.change(titleBox, { target: { value: '' } })
    fireEvent.blur(titleBox)
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(mockApi.docs.update).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('note card with no body shows the empty placeholder', async () => {
    mockApi.docs.list.mockResolvedValue([{ ...DOC_SUMMARY, excerpt: '   ' }])
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Empty note')).toBeTruthy())
  })

  // Notes = this same panel locked to doc_type 'note' (Layout renders it as the Notes view).
  it('docType="note" filters the list and creates from the Keep-style composer', async () => {
    mockApi.docs.list.mockResolvedValue([])
    mockApi.docs.create.mockResolvedValue(DOC_FULL)
    mockApi.docs.get.mockResolvedValue(DOC_FULL)
    render(<DocsPanel projectId="proj_1" docType="note" onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText(/No notes yet/i)).toBeTruthy())
    expect(mockApi.docs.list).toHaveBeenCalledWith('proj_1', { doc_type: 'note', q: '' })

    // No "+ New Note" button and no type dropdown — the composer replaces both.
    expect(screen.queryByText('+ New Note')).toBeNull()
    expect(screen.queryByText('Type')).toBeNull()
    fireEvent.change(screen.getByPlaceholderText('Take a note…'), { target: { value: 'Groceries' } })
    fireEvent.keyDown(screen.getByPlaceholderText('Take a note…'), { key: 'Enter' })

    await waitFor(() =>
      expect(mockApi.docs.create).toHaveBeenCalledWith('proj_1', {
        title: 'Groceries',
        doc_type: 'note',
      })
    )
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

  // The handles are hover-driven and positioned from bounding rects, so what is
  // worth pinning here is the wiring: the pointed-at cell decides which column
  // and row the commands hit, and the "+" appends at the far end of the table.
  it('table hover handles add a column and delete the pointed-at row', async () => {
    const cell = (type: string, text: string) =>
      ({ type, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] })
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    // Leaving the editor flushes a save; without this the unmount path throws.
    mockApi.docs.update.mockResolvedValue({ ...DOC_FULL, version: 2 })
    mockApi.docs.get.mockResolvedValue({
      ...DOC_FULL,
      content_json: JSON.stringify({
        type: 'doc',
        content: [{
          type: 'table',
          content: [
            { type: 'tableRow', content: [cell('tableHeader', 'A'), cell('tableHeader', 'B')] },
            { type: 'tableRow', content: [cell('tableCell', '1'), cell('tableCell', '2')] },
          ],
        }],
      }),
    })

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))
    await waitFor(() => screen.getByLabelText('Title'))
    fireEvent.click(screen.getByText('Edit'))

    const bodyCell = await waitFor(() => {
      const td = document.querySelector('.ab-prose td')
      if (!td) throw new Error('table not rendered')
      return td
    })
    // No handles until the pointer is actually over a cell.
    expect(screen.queryByTitle('Add column right')).toBeNull()

    fireEvent.mouseMove(bodyCell)
    // Every handle hangs outside the table, so the pointer crosses non-cell
    // ground to reach one. That must not be read as "left the table".
    fireEvent.mouseMove(document.querySelector('.dp-tiptap-wrap')!)
    fireEvent.click(screen.getByTitle('Add column right'))
    await waitFor(() =>
      expect(document.querySelectorAll('.ab-prose tr')[0].children.length).toBe(3))

    fireEvent.mouseMove(document.querySelector('.ab-prose td')!)
    fireEvent.click(screen.getByTitle('Delete row'))
    await waitFor(() => expect(document.querySelectorAll('.ab-prose tr').length).toBe(1))

    // Handle edits are ordinary transactions, so they sit in the same undo
    // stack as typing — including from the toolbar, where the click has just
    // taken focus off the editor.
    fireEvent.click(screen.getByTitle('Undo (Ctrl+Z)'))
    await waitFor(() => expect(document.querySelectorAll('.ab-prose tr').length).toBe(2))
    fireEvent.click(screen.getByTitle('Undo (Ctrl+Z)'))
    await waitFor(() =>
      expect(document.querySelectorAll('.ab-prose tr')[0].children.length).toBe(2))
  })

  it('a doc opens read-only, and Edit arms the title, the toolbar and Save', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))
    await waitFor(() => screen.getByLabelText('Title'))

    expect((screen.getByLabelText('Title') as HTMLInputElement).disabled).toBe(true)
    expect(screen.queryByRole('toolbar', { name: 'Editor toolbar' })).toBeNull()
    expect(screen.queryByText('Save')).toBeNull()
    expect(screen.getByText(/Read-only/)).toBeTruthy()

    fireEvent.click(screen.getByText('Edit'))

    expect((screen.getByLabelText('Title') as HTMLInputElement).disabled).toBe(false)
    expect(screen.getByRole('toolbar', { name: 'Editor toolbar' })).toBeTruthy()
    expect(screen.getByText('Save')).toBeTruthy()
    expect(screen.getByText('Done')).toBeTruthy()
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
      new Error('409: {"detail":"The exported Markdown file was changed outside Planarus. Review it before exporting again."}'),
    )
    const confirmSpy = vi.spyOn(window, 'confirm')

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))
    await waitFor(() => expect(mockApi.docs.get).toHaveBeenCalled())
    await waitFor(() => screen.getByText('Export Markdown'))

    fireEvent.click(screen.getByText('Export Markdown'))
    await waitFor(() =>
      expect(screen.getByText(/changed outside Planarus/i)).toBeTruthy(),
    )
    // exportMarkdown called exactly once — no force-retry
    expect(mockApi.docs.exportMarkdown).toHaveBeenCalledTimes(1)
    // No confirm dialog was shown
    expect(confirmSpy).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  // #183 step 3c: /docs/:docSlug — ProjectRoute resolves the slug to an id
  // and passes it down as initialDocId; DocsPanel reports every open/close
  // back through onDocSelected so the URL can follow.
  it('#183 step 3c: selecting a doc from the list calls onDocSelected, for the URL to follow', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)
    const onDocSelected = vi.fn()

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} onDocSelected={onDocSelected} />)
    await waitFor(() => screen.getByText('Test Note'))
    fireEvent.click(screen.getByText('Test Note'))

    expect(onDocSelected).toHaveBeenCalledWith('doc_1')
  })

  it('#183 step 3c: initialDocId opens that doc directly', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} initialDocId="doc_1" />)

    expect(await screen.findByLabelText('Title')).toBeTruthy()
    expect((screen.getByLabelText('Title') as HTMLInputElement).value).toBe('Test Note')
  })

  it('#183 step 3c: going back to the list calls onDocSelected(null)', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockResolvedValue(DOC_FULL)
    const onDocSelected = vi.fn()

    render(
      <DocsPanel projectId="proj_1" onClose={vi.fn()} initialDocId="doc_1" onDocSelected={onDocSelected} />,
    )
    await screen.findByLabelText('Title')
    fireEvent.click(screen.getByTitle('Back to list'))

    expect(onDocSelected).toHaveBeenCalledWith(null)
    await waitFor(() => expect(screen.getByText('Test Note')).toBeTruthy()) // back on the list
  })

  it('#183 step 3c: an unresolvable initialDocId fails silently, staying on the list', async () => {
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
    mockApi.docs.get.mockRejectedValue(new Error('404: not found'))

    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} initialDocId="doc_gone" />)

    await waitFor(() => expect(screen.getByText('Test Note')).toBeTruthy())
    expect(screen.queryByLabelText('Title')).toBeNull()
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
        PlanarusMention, ChildPage, Callout,
        Details, DetailsSummary, DetailsContent,
        Table, TableRow, TableHeader, TableCell,
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

  // #118: `markdown_cache` is serialized from whatever JSON is stored, and a
  // stored document can predate the URI policy or arrive by import. A crafted
  // href used to be written raw, so an unbalanced ")" closed the link early and
  // the rest of the URL landed in the exported file as prose — or as a second,
  // attacker-chosen link. Content is injected as JSON on purpose: HTML would go
  // through the link mark's own parse-time validation and never reach the
  // serializer, which is the code under test.
  it('cannot have its link syntax broken by a crafted href', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'paragraph',
          content: [{
            type: 'text', text: 'click',
            marks: [{ type: 'link', attrs: { href: 'https://x.test/a)](javascript:alert(1)' } }],
          }],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('[click](<https://x.test/a)](javascript:alert(1)>)')
    // The whole destination sits inside one angle-bracket pair, which is the
    // Markdown form that may hold a ")". The injected "](" is therefore part of
    // one URL rather than the start of a second, attacker-chosen link — and
    // markdownUrl percent-encodes "<"/">" so nothing can close the pair early.
    expect(md).toMatch(/^\[click\]\(<[^<>]*>\)/m)
  })

  it('cannot have its link title broken by a crafted title', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'paragraph',
          content: [{
            type: 'text', text: 'click',
            marks: [{ type: 'link', attrs: { href: 'https://x.test/', title: 'a") [x](evil:' } }],
          }],
        }],
      })
    })
    expect(serializeToMarkdown(editor.state.doc)).toContain('"a\\") [x](evil:"')
  })

  it('cannot have its image syntax broken by a crafted src', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{ type: 'image', attrs: { src: 'https://x.test/a b).png', alt: 'x' } }],
      })
    })
    expect(serializeToMarkdown(editor.state.doc)).toContain('![x](<https://x.test/a b).png>)')
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

  // #138 plan 23/24: mention and childPage both serialize to the same
  // planarus:// scheme, so markdown_cache/search/AI reads see references and
  // nesting uniformly.
  it('serializes a mention to [label](planarus://type/id)', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'paragraph',
          content: [{ type: 'mention', attrs: { targetType: 'task', targetId: 'task_abc', label: 'Fix bug' } }],
        }],
      })
    })
    expect(serializeToMarkdown(editor.state.doc)).toContain('[Fix bug](planarus://task/task_abc)')
  })

  it('serializes a childPage to [title](planarus://doc/id)', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{ type: 'childPage', attrs: { docId: 'doc_child1', title: 'Sub page' } }],
      })
    })
    expect(serializeToMarkdown(editor.state.doc)).toContain('[Sub page](planarus://doc/doc_child1)')
  })

  it('round-trips a callout without crashing the save, prefixed by its icon', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'callout', attrs: { icon: '💡' },
          content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Heads up' }] }],
        }],
      })
    })
    expect(serializeToMarkdown(editor.state.doc)).toContain('> 💡 Heads up')
  })

  it('round-trips a toggle (details/summary/content) without crashing the save', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'details',
          content: [
            { type: 'detailsSummary', content: [{ type: 'text', text: 'More' }] },
            { type: 'detailsContent', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Hidden text' }] }] },
          ],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('**More**')
    expect(md).toContain('Hidden text')
  })

  // #138: the #118 precedent ("cannot have its link syntax broken by a crafted
  // href") extended to the five new handlers. These node attrs are set by
  // parseHTML from data-* on pasted HTML and by any content_json write incl. the
  // MCP doc.update propose path, so none of them passed through isAllowedLink.
  // markdown_cache feeds disk exports, the context pack and MCP reads, so a
  // forged construct here is both markdown forgery and a prompt-injection channel.
  const FORGERY = 'x\n\n# Injected\n\n[Click me](https://evil.test)\n\n'

  it('a crafted callout icon cannot escape the blockquote', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'callout', attrs: { icon: FORGERY },
          content: [{ type: 'paragraph', content: [{ type: 'text', text: 'body' }] }],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).not.toContain('# Injected')
    expect(md).not.toContain('[Click me](https://evil.test)')
    // Falls back to the allowlisted default rather than emitting the forgery.
    expect(md).toContain('> 💡 body')
  })

  it('a crafted mention label cannot forge a second link or leave its line', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'paragraph',
          content: [{ type: 'mention', attrs: { targetType: 'task', targetId: 'tsk_1', label: FORGERY } }],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    // The forged link must not parse — brackets are escaped, so it stays text.
    expect(md).not.toContain('[Click me](https://evil.test)')
    expect(md).toContain('\\[Click me\\]')
    // Collapsed onto one line, so "#" can never sit at start-of-line and become
    // a heading, and the label cannot escape its own [...] construct.
    expect(md.trimEnd().split('\n').every(l => !l.startsWith('#'))).toBe(true)
    expect(md.split('\n').filter(l => l.includes('planarus://'))).toHaveLength(1)
  })

  it('a crafted mention targetId cannot break the link destination', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'paragraph',
          content: [{ type: 'mention', attrs: { targetType: 'task', targetId: 'a\n\n[evil](https://evil.test)', label: 'ref' } }],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).not.toContain('[evil](https://evil.test)')
    // The out-of-shape id is dropped rather than escaped into the destination.
    expect(md).toContain('[ref](planarus://task/)')
  })

  it('a crafted childPage title cannot forge markdown', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{ type: 'childPage', attrs: { docId: 'doc_1', title: FORGERY } }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).not.toContain('[Click me](https://evil.test)')
    expect(md).toContain('\\[Click me\\]')
    expect(md.trimEnd().split('\n').every(l => !l.startsWith('#'))).toBe(true)
    expect(md.split('\n').filter(l => l.includes('planarus://'))).toHaveLength(1)
  })

  it('table cell text cannot forge a link or break out of the row', () => {
    const cell = (text: string) => ({ type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] })
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'table',
          content: [
            { type: 'tableRow', content: [cell('[x](https://evil.test)'), cell('b\rc')] },
          ],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    // Literal characters typed into a cell must not become a real link.
    expect(md).not.toContain('[x](https://evil.test)')
    // A lone \r is a CommonMark line ending — it must not end the row.
    const rows = md.split('\n').filter(l => l.trim().startsWith('|'))
    expect(rows.every(l => l.trim().endsWith('|'))).toBe(true)
  })

  it('round-trips a table to a GFM table without crashing the save', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'table',
          content: [
            { type: 'tableRow', content: [
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'A' }] }] },
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'B' }] }] },
            ] },
            { type: 'tableRow', content: [
              { type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text: '1' }] }] },
              { type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text: '2' }] }] },
            ] },
          ],
        }],
      })
    })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('| A | B |')
    expect(md).toContain('| --- | --- |')
    expect(md).toContain('| 1 | 2 |')
  })

  // What the toolbar's table buttons run. The serializer writes the GFM
  // delimiter row from the header's cell count, so a table that grew a column
  // has to keep the two in step or every downstream markdown reader sees a
  // malformed table.
  it('a table that gains a column and a row still serializes as valid GFM', () => {
    act(() => {
      editor.commands.setContent({
        type: 'doc',
        content: [{
          type: 'table',
          content: [
            { type: 'tableRow', content: [
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'A' }] }] },
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'B' }] }] },
            ] },
            { type: 'tableRow', content: [
              { type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text: '1' }] }] },
              { type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text: '2' }] }] },
            ] },
          ],
        }],
      })
    })
    // pos 4 = inside the first header cell's paragraph; the table commands act
    // on whichever cell holds the selection.
    act(() => { editor.chain().setTextSelection(4).addColumnAfter().addRowAfter().run() })
    const md = serializeToMarkdown(editor.state.doc)
    expect(md).toContain('| A |  | B |')
    expect(md).toContain('| --- | --- | --- |')
    expect(md.split('\n').filter(l => l.startsWith('|'))).toHaveLength(4)
  })
})
