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
})
