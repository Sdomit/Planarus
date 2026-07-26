import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DocsPanel from './DocsPanel'

// Excalidraw pulls in browser-only modules that crash under jsdom at import
// time (see CanvasEditor.tsx's own comment on the lazy import) — replaced with
// a stub that renders nothing but still resolves `excalidrawAPI`, since the
// point of this file is the connections section CanvasEditor now renders
// alongside it, not canvas editing itself.
vi.mock('@excalidraw/excalidraw', () => ({
  Excalidraw: () => null,
  serializeAsJSON: () => '{}',
  convertToExcalidrawElements: (els: unknown) => els,
}))

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
    comments: { list: vi.fn().mockResolvedValue([]) },
  },
}))

import { api } from '../api/client'

type Mocked = ReturnType<typeof vi.fn>
const mockApi = api as unknown as {
  docs: Record<string, Mocked>
  connections: Record<string, Mocked>
  phases: Record<string, Mocked>
  tasks: Record<string, Mocked>
  milestones: Record<string, Mocked>
  decisions: Record<string, Mocked>
  risks: Record<string, Mocked>
}

const CANVAS_SUMMARY = {
  id: 'doc_canvas', project_id: 'proj_1', parent_doc_id: null, title: 'Roadmap sketch',
  slug: 'roadmap-sketch', doc_type: 'canvas', status: 'draft', sort_order: 0, version: 1,
  updated_at: '2026-07-26T00:00:00+00:00', archived_at: null, editor_format: 'excalidraw',
}
const CANVAS_FULL = {
  ...CANVAS_SUMMARY,
  content_json: '{"elements":[],"appState":{},"files":{}}',
  markdown_cache: '', export_relative_path: null, export_checksum: null,
  exported_at: null, created_at: '2026-07-26T00:00:00+00:00',
}

const TASK = { id: 'tsk_1', title: 'Ship the spine', status: 'in_progress', phase_id: null }
const REFERENCE = {
  id: 'con_1', project_id: 'proj_1', relation_type: 'references',
  source_entity_type: 'task', source_entity_id: 'tsk_1',
  target_entity_type: 'doc', target_entity_id: 'doc_canvas',
  created_at: 'x', updated_at: 'x',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.docs.list.mockResolvedValue([CANVAS_SUMMARY])
  mockApi.docs.get.mockResolvedValue(CANVAS_FULL)
  mockApi.connections.list.mockResolvedValue([REFERENCE])
  mockApi.phases.list.mockResolvedValue([])
  mockApi.tasks.list.mockResolvedValue([TASK])
  mockApi.milestones.list.mockResolvedValue([])
  mockApi.decisions.list.mockResolvedValue([])
  mockApi.risks.list.mockResolvedValue([])
})

afterEach(() => { cleanup(); vi.useRealTimers() })

describe('Canvas connections (Codex #173 P2 — canvas docs are still Documents)', () => {
  it('renders the connections section for a canvas document', async () => {
    render(<DocsPanel projectId="proj_1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByText('Roadmap sketch'))
    // Before this fix, EntityConnections lived only inside DocEditor —
    // CanvasEditor rendered as its sibling alternative and never got it, so a
    // canvas's connections were invisible and unremovable from the canvas view.
    expect(await screen.findByText('Referenced by')).toBeTruthy()
    expect(screen.getByText('Ship the spine')).toBeTruthy()
  })
})
