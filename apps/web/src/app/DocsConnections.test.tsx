import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import DocsPanel from './DocsPanel'
import { ConnectionProvider, EntityConnections } from './EntityConnections'
import type { ConnectionTarget } from './EntityConnections'
import type { EntityConnection } from '../api/client'

// The create-then-navigate test lands on a *canvas* doc rather than a Tiptap
// one deliberately: a pre-existing, unrelated bug in DocEditor's create->editor
// transition throws under jsdom regardless of this feature (verified against
// unmodified `main`), and a canvas doc's editor never touches that code path.
vi.mock('@excalidraw/excalidraw', () => ({
  Excalidraw: () => null,
  serializeAsJSON: () => '{}',
  convertToExcalidrawElements: (els: unknown) => els,
}))

// Unlike DocsPanel.test.tsx this mock carries the planning namespaces too — the
// connections section needs them to label its endpoints.
vi.mock('../api/client', () => ({
  api: {
    docs: {
      list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
      exportMarkdown: vi.fn(),
      presenceBeat: vi.fn().mockRejectedValue(new Error('404: not found')),
      presenceLeave: vi.fn().mockResolvedValue(undefined),
    },
    connections: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
    phases: { list: vi.fn() },
    tasks: { list: vi.fn() },
    milestones: { list: vi.fn() },
    decisions: { list: vi.fn() },
    risks: { list: vi.fn() },
  },
}))

import { api } from '../api/client'

type Mocked = ReturnType<typeof vi.fn>
// `connections` is optional so one test can delete it entirely and exercise the
// synchronous-TypeError path.
const mockApi = api as unknown as {
  docs: Record<string, Mocked>
  connections?: Record<string, Mocked>
  phases: Record<string, Mocked>
  tasks: Record<string, Mocked>
  milestones: Record<string, Mocked>
  decisions: Record<string, Mocked>
  risks: Record<string, Mocked>
}

const DOC_SUMMARY = {
  id: 'doc_1', project_id: 'proj_1', parent_doc_id: null, title: 'Architecture',
  slug: 'architecture', doc_type: 'note', status: 'draft', sort_order: 0, version: 1,
  updated_at: '2026-07-26T00:00:00+00:00', archived_at: null, editor_format: 'tiptap_json',
}
const DOC_FULL = {
  ...DOC_SUMMARY,
  content_json: '{"type": "doc", "content": [{"type": "paragraph"}]}',
  markdown_cache: '', export_relative_path: null, export_checksum: null,
  exported_at: null, created_at: '2026-07-26T00:00:00+00:00',
}

const TASK = { id: 'tsk_1', title: 'Ship the spine', status: 'in_progress', phase_id: 'phs_1' }
const PHASE = { id: 'phs_1', title: 'Phase 2', status: 'active' }

// A task that references this doc — the doc is the canonical *target*.
const REFERENCE: EntityConnection = {
  id: 'con_1', project_id: 'proj_1', relation_type: 'references',
  source_entity_type: 'task', source_entity_id: 'tsk_1',
  target_entity_type: 'doc', target_entity_id: 'doc_1',
  created_at: 'x', updated_at: 'x',
}

function seed({ connections = [REFERENCE] }: { connections?: EntityConnection[] } = {}) {
  mockApi.docs.list.mockResolvedValue([DOC_SUMMARY])
  mockApi.docs.get.mockResolvedValue(DOC_FULL)
  mockApi.connections!.list.mockResolvedValue(connections)
  mockApi.phases.list.mockResolvedValue([PHASE])
  mockApi.tasks.list.mockResolvedValue([TASK])
  mockApi.milestones.list.mockResolvedValue([])
  mockApi.decisions.list.mockResolvedValue([])
  mockApi.risks.list.mockResolvedValue([])
}

async function openTheDoc() {
  render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
  fireEvent.click(await screen.findByText('Architecture'))
}

beforeEach(() => { vi.clearAllMocks() })
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('Docs connections (plan 25 — extend the section to Documents)', () => {
  it('shows who references the document, using the reverse label', async () => {
    seed()
    await openTheDoc()
    expect(await screen.findByText('Referenced by')).toBeTruthy()
    // The referencing task is named, and carries its resolved phase context —
    // not a raw id.
    expect(screen.getByText('Ship the spine')).toBeTruthy()
    expect(screen.getByText('Phase 2 · in progress')).toBeTruthy()
  })

  it('does not fetch the connection graph while only browsing the list', async () => {
    seed()
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    await screen.findByText('Architecture')
    // Opening the panel must stay as cheap as it was before this feature.
    expect(mockApi.connections!.list).not.toHaveBeenCalled()
    expect(mockApi.tasks.list).not.toHaveBeenCalled()
  })

  it('does not remount the editor when the graph finishes loading', async () => {
    seed()
    await openTheDoc()
    await screen.findByText('Referenced by')
    // The regression this guards: conditionally *wrapping* the editor in the
    // provider changes the element type at that position, so React unmounts and
    // remounts it the moment loading completes — refetching the document and
    // discarding the live Tiptap instance (and with it any unsaved edit).
    expect(mockApi.docs.get).toHaveBeenCalledTimes(1)
  })

  it('loads the graph once, not again per document opened', async () => {
    seed()
    await openTheDoc()
    await screen.findByText('Referenced by')
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    fireEvent.click(await screen.findByText('Architecture'))
    await screen.findByText('Referenced by')
    expect(mockApi.connections!.list).toHaveBeenCalledTimes(1)
  })

  it('keeps the editor usable when the connection graph cannot be loaded', async () => {
    seed()
    mockApi.connections!.list.mockRejectedValue(new Error('offline'))
    await openTheDoc()
    // The doc still opens; the section is simply absent.
    await waitFor(() => expect(screen.getByLabelText('Title')).toBeTruthy())
    expect(screen.queryByText('Referenced by')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add connection' })).toBeNull()
  })

  it('survives an api client with no connections namespace at all', async () => {
    seed()
    const saved = mockApi.connections
    // A synchronous TypeError at property access — the failure mode a per-call
    // .catch() cannot see, because no promise exists yet to attach it to.
    mockApi.connections = undefined
    try {
      await openTheDoc()
      await waitFor(() => expect(screen.getByLabelText('Title')).toBeTruthy())
      expect(screen.queryByText('Referenced by')).toBeNull()
    } finally {
      mockApi.connections = saved
    }
  })
})

describe('Docs connections stay live across create/delete (Codex #173 P2)', () => {
  it('a document created after the graph loaded is immediately a selectable target', async () => {
    seed()
    // A canvas doc: its editor never touches Tiptap, only Excalidraw (stubbed
    // above), which sidesteps the pre-existing create->editor bug entirely —
    // irrelevant to what this test checks (target-list staleness).
    const created = {
      id: 'doc_2', project_id: 'proj_1', title: 'Runbook', doc_type: 'canvas', status: 'draft',
      editor_format: 'excalidraw',
    }
    const createdFull = {
      ...created,
      content_json: '{"elements":[],"appState":{},"files":{}}',
      markdown_cache: '', export_relative_path: null, export_checksum: null,
      exported_at: null, created_at: 'x', version: 1, archived_at: null,
    }
    mockApi.docs.create = vi.fn().mockResolvedValue(created)
    mockApi.docs.get.mockImplementation((id: string) =>
      Promise.resolve(id === 'doc_2' ? createdFull : DOC_FULL))

    await openTheDoc()
    await screen.findByText('Referenced by') // graph has loaded once

    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    fireEvent.click(await screen.findByText('+ New Doc'))
    fireEvent.change(screen.getByPlaceholderText('Doc title'), { target: { value: 'Runbook' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'canvas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    // Creation navigates straight into the new doc's (canvas) editor; back out
    // to reach the original document again.
    await waitFor(() => expect(mockApi.docs.create).toHaveBeenCalled())
    fireEvent.click(await screen.findByRole('button', { name: /Back/ }))
    fireEvent.click(await screen.findByText('Architecture'))
    await screen.findByText('Referenced by')

    fireEvent.click(screen.getByRole('button', { name: 'Add connection' }))
    fireEvent.change(screen.getByLabelText('Relationship for Architecture'), { target: { value: 'related_to' } })
    const picker = screen.getByLabelText('Connect Architecture to') as HTMLSelectElement
    // Before the fix this list would not contain the doc created after the
    // graph's one-time load — it stayed invisible until the whole panel
    // remounted (a project switch), exactly Codex's reported repro.
    expect([...picker.options].map(o => o.textContent).join('|')).toContain('Runbook')
  })

  it('deleting a document drops it as a target and prunes any connection to it', async () => {
    const otherDoc = { id: 'doc_2', title: 'Runbook', doc_type: 'spec', status: 'draft' }
    const crossDocLink: EntityConnection = {
      id: 'con_2', project_id: 'proj_1', relation_type: 'related_to',
      source_entity_type: 'doc', source_entity_id: 'doc_1',
      target_entity_type: 'doc', target_entity_id: 'doc_2',
      created_at: 'x', updated_at: 'x',
    }
    seed({ connections: [REFERENCE, crossDocLink] })
    mockApi.docs.list.mockResolvedValue([DOC_SUMMARY, otherDoc])
    // Distinct per id — `seed()`'s blanket mock would resolve doc_1's own data
    // for doc_2 too, and `remove()` reads the id to delete from this response.
    const otherFull = {
      ...otherDoc, project_id: 'proj_1', slug: 'runbook', sort_order: 1, version: 1,
      updated_at: 'x', archived_at: null, editor_format: 'tiptap_json',
      content_json: '{"type":"doc","content":[{"type":"paragraph"}]}',
      markdown_cache: '', export_relative_path: null, export_checksum: null,
      exported_at: null, created_at: 'x',
    }
    mockApi.docs.get.mockImplementation((id: string) =>
      Promise.resolve(id === 'doc_2' ? otherFull : DOC_FULL))

    await openTheDoc()
    // Both the task reference and the cross-doc link are visible while doc_2
    // still exists.
    expect(await screen.findByText('Related to')).toBeTruthy()
    expect(screen.getByText('Runbook')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    fireEvent.click(await screen.findByText('Runbook'))
    await screen.findByLabelText('Title')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockApi.docs.remove.mockResolvedValue(undefined)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(mockApi.docs.remove).toHaveBeenCalledWith('doc_2'))

    fireEvent.click(await screen.findByText('Architecture'))
    // The genuinely-live reference survives; the connection to the now-deleted
    // document is pruned automatically once it drops out of `targets`.
    await screen.findByText('Referenced by')
    expect(screen.queryByText('Related to')).toBeNull()
    expect(screen.queryByText('Runbook')).toBeNull()
  })
})

describe('ConnectionProvider pruning vs. a not-yet-loaded target list', () => {
  const DOC_TARGETS: ConnectionTarget[] = [
    { entityType: 'doc', id: 'doc_1', title: 'Architecture', meta: 'note · draft' },
    { entityType: 'task', id: 'tsk_1', title: 'Ship the spine', meta: 'Phase 2 · in progress' },
  ]

  function Harness({ ready, targets }: { ready?: boolean; targets: ConnectionTarget[] }) {
    const [connections, setConnections] = useState<EntityConnection[]>([REFERENCE])
    return (
      <ConnectionProvider
        connections={connections} setConnections={setConnections}
        targets={targets} ready={ready}
      >
        <EntityConnections projectId="proj_1" entityType="doc" entityId="doc_1" label="Architecture" />
      </ConnectionProvider>
    )
  }

  it('prunes a genuinely dangling connection once loaded', () => {
    // The behaviour the effect exists for: the task endpoint is gone, so the
    // connection to it goes too rather than rendering "Unavailable item".
    render(<Harness ready targets={[DOC_TARGETS[0]]} />)
    expect(screen.getByText('No connections yet.')).toBeTruthy()
  })

  it('keeps connections while the target list is still loading', () => {
    // Without the `ready` guard an empty target list reads as "every endpoint
    // was deleted" and clears local state — the collection would be gone before
    // the fetch that fills it ever resolves.
    render(<Harness ready={false} targets={[]} />)
    expect(screen.queryByText('No connections yet.')).toBeNull()
    // Nothing renders at all until ready, so the composer cannot be opened
    // against an empty picker either.
    expect(screen.queryByRole('button', { name: 'Add connection' })).toBeNull()
  })

  it('shows the connection once both halves have landed', () => {
    render(<Harness ready targets={DOC_TARGETS} />)
    expect(screen.getByText('Referenced by')).toBeTruthy()
    expect(screen.getByText('Ship the spine')).toBeTruthy()
  })
})
