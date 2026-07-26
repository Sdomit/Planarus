import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ConnectionProvider, EntityConnections } from './EntityConnections'
import type { ConnectionTarget } from './EntityConnections'
import type { EntityConnection } from '../api/client'

vi.mock('../api/client', () => ({
  api: { connections: { create: vi.fn(), remove: vi.fn() } },
}))

import { api } from '../api/client'

const mockConnections = api.connections as unknown as { create: ReturnType<typeof vi.fn>; remove: ReturnType<typeof vi.fn> }

const targets: ConnectionTarget[] = [
  { entityType: 'task', id: 'tsk_1', title: 'Write migration notes', meta: 'ready' },
  { entityType: 'decision', id: 'dec_1', title: 'Keep data local', meta: 'accepted' },
  { entityType: 'risk', id: 'rsk_1', title: 'Migration delay', meta: 'open' },
]

const implementation: EntityConnection = {
  id: 'con_1', project_id: 'proj_1', relation_type: 'implements',
  source_entity_type: 'task', source_entity_id: 'tsk_1', target_entity_type: 'decision', target_entity_id: 'dec_1',
  created_at: '2026-07-22T00:00:00Z', updated_at: '2026-07-22T00:00:00Z',
}

function ConnectionDetail({ initial = [] }: { initial?: EntityConnection[] }) {
  const [connections, setConnections] = useState(initial)
  return (
    <ConnectionProvider connections={connections} setConnections={setConnections} targets={targets}>
      <EntityConnections projectId="proj_1" entityType="decision" entityId="dec_1" label="Keep data local" />
    </ConnectionProvider>
  )
}

// Phase and Doc (plan 25's affordance table) — the two types that rendered
// nothing before, because `choicesFor` had no entry and the component returns
// null for an unknown type.
const wideTargets: ConnectionTarget[] = [
  ...targets,
  { entityType: 'phase', id: 'phs_1', title: 'Phase 2', meta: 'active' },
  { entityType: 'doc', id: 'doc_1', title: 'Architecture notes', meta: 'spec · draft' },
]

function TypedDetail({
  entityType, entityId, label, initial = [],
}: {
  entityType: 'phase' | 'doc'
  entityId: string
  label: string
  initial?: EntityConnection[]
}) {
  const [connections, setConnections] = useState(initial)
  return (
    <ConnectionProvider connections={connections} setConnections={setConnections} targets={wideTargets}>
      <EntityConnections projectId="proj_1" entityType={entityType} entityId={entityId} label={label} />
    </ConnectionProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('EntityConnections', () => {
  it('uses the reverse label while storing the canonical task-to-decision direction', async () => {
    mockConnections.create.mockResolvedValue(implementation)
    render(<ConnectionDetail />)

    fireEvent.click(screen.getByRole('button', { name: 'Add connection' }))
    fireEvent.change(screen.getByLabelText('Connect Keep data local to'), { target: { value: 'task:tsk_1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(mockConnections.create).toHaveBeenCalledWith('proj_1', {
      relation_type: 'implements',
      source_entity_type: 'task', source_entity_id: 'tsk_1',
      target_entity_type: 'decision', target_entity_id: 'dec_1',
    }))
    expect(await screen.findByText('Implemented by')).toBeTruthy()
    expect(screen.getByText('Write migration notes')).toBeTruthy()
  })

  it('removes only after the local API accepts the request', async () => {
    mockConnections.remove.mockResolvedValue(undefined)
    render(<ConnectionDetail initial={[implementation]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Remove connection to Write migration notes' }))
    await waitFor(() => expect(mockConnections.remove).toHaveBeenCalledWith('con_1'))
    expect(await screen.findByText('No connections yet.')).toBeTruthy()
  })

  // --- Phase and Document (plan 25 affordance table) ------------------------

  it('a phase can reference a document, and offers only documents for it', async () => {
    mockConnections.create.mockResolvedValue({
      id: 'con_p', project_id: 'proj_1', relation_type: 'references',
      source_entity_type: 'phase', source_entity_id: 'phs_1',
      target_entity_type: 'doc', target_entity_id: 'doc_1',
      created_at: 'x', updated_at: 'x',
    })
    render(<TypedDetail entityType="phase" entityId="phs_1" label="Phase 2" />)

    fireEvent.click(screen.getByRole('button', { name: 'Add connection' }))
    // "References" targets docs only — a phase must not be offered a task here,
    // because the API's relation matrix has no ("phase","task") pair to store it.
    const picker = screen.getByLabelText('Connect Phase 2 to') as HTMLSelectElement
    const optionText = [...picker.options].map(o => o.textContent).join('|')
    expect(optionText).toContain('Architecture notes')
    expect(optionText).not.toContain('Write migration notes')

    fireEvent.change(picker, { target: { value: 'doc:doc_1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    // Phase is the source for `references`; the doc is the target.
    await waitFor(() => expect(mockConnections.create).toHaveBeenCalledWith('proj_1', {
      relation_type: 'references',
      source_entity_type: 'phase', source_entity_id: 'phs_1',
      target_entity_type: 'doc', target_entity_id: 'doc_1',
    }))
    expect(await screen.findByText('References')).toBeTruthy()
  })

  it('a document stores the canonical item-to-doc direction under "Referenced by"', async () => {
    mockConnections.create.mockResolvedValue({
      id: 'con_d', project_id: 'proj_1', relation_type: 'references',
      source_entity_type: 'task', source_entity_id: 'tsk_1',
      target_entity_type: 'doc', target_entity_id: 'doc_1',
      created_at: 'x', updated_at: 'x',
    })
    render(<TypedDetail entityType="doc" entityId="doc_1" label="Architecture notes" />)

    fireEvent.click(screen.getByRole('button', { name: 'Add connection' }))
    fireEvent.change(screen.getByLabelText('Connect Architecture notes to'), { target: { value: 'task:tsk_1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    // The doc is the *target*, exactly as the relation matrix requires — the
    // reverse-form label must not invert what gets stored.
    await waitFor(() => expect(mockConnections.create).toHaveBeenCalledWith('proj_1', {
      relation_type: 'references',
      source_entity_type: 'task', source_entity_id: 'tsk_1',
      target_entity_type: 'doc', target_entity_id: 'doc_1',
    }))
    expect(await screen.findByText('Referenced by')).toBeTruthy()
    expect(screen.getByText('Write migration notes')).toBeTruthy()
  })

  it('a document never offers itself as its own connection target', () => {
    render(<TypedDetail entityType="doc" entityId="doc_1" label="Architecture notes" />)
    fireEvent.click(screen.getByRole('button', { name: 'Add connection' }))
    // Switch to "Related to", the only choice whose target types include docs.
    fireEvent.change(screen.getByLabelText('Relationship for Architecture notes'), { target: { value: 'related_to' } })
    const picker = screen.getByLabelText('Connect Architecture notes to') as HTMLSelectElement
    expect([...picker.options].map(o => o.value)).not.toContain('doc:doc_1')
  })
})
