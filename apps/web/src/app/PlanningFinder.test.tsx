import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { ConnectionProvider } from './EntityConnections'
import { usePlanningFinder } from './PlanningFinder'
import type { EntityConnection } from '../api/client'
import type { ConnectionTarget } from './EntityConnections'

const targets: ConnectionTarget[] = [
  { entityType: 'task', id: 'task_1', title: 'Ship release', meta: 'ready' },
  { entityType: 'task', id: 'task_2', title: 'Write docs', meta: 'backlog' },
  { entityType: 'decision', id: 'decision_1', title: 'Keep it local', meta: 'accepted' },
]

const connections: EntityConnection[] = [{
  id: 'connection_1', project_id: 'project_1', relation_type: 'implements',
  source_entity_type: 'task', source_entity_id: 'task_1',
  target_entity_type: 'decision', target_entity_id: 'decision_1',
  created_at: 'x', updated_at: 'x',
}]

function TaskFinder() {
  const [state, setState] = useState(connections)
  return (
    <ConnectionProvider connections={state} setConnections={setState} targets={targets}>
      <FinderBody />
    </ConnectionProvider>
  )

  function FinderBody() {
    const nestedFinder = usePlanningFinder({
      label: 'tasks',
      items: targets.filter(target => target.entityType === 'task'),
      entityType: 'task',
      searchText: item => `${item.title} ${item.meta}`,
    })
    return <>{nestedFinder.controls}{nestedFinder.filtered.map(item => <p key={item.id}>{item.title}</p>)}</>
  }
}

function AttachmentFinder() {
  const [state, setState] = useState(connections)
  const comments = [
    { id: 'comment_1', entity_type: 'task', entity_id: 'task_1', body: 'Ready to ship' },
    { id: 'comment_2', entity_type: 'task', entity_id: 'task_2', body: 'Draft first' },
  ]
  return (
    <ConnectionProvider connections={state} setConnections={setState} targets={targets}>
      <AttachmentBody comments={comments} />
    </ConnectionProvider>
  )
}

function AttachmentBody({ comments }: { comments: { id: string; entity_type: string; entity_id: string; body: string }[] }) {
  const finder = usePlanningFinder({
    label: 'comments', items: comments, searchText: item => item.body,
    attachmentHost: item => ({ entity_type: item.entity_type, entity_id: item.entity_id }),
  })
  return <>{finder.controls}{finder.filtered.map(item => <p key={item.id}>{item.body}</p>)}</>
}

describe('usePlanningFinder', () => {
  afterEach(cleanup)

  it('filters text live without case sensitivity', () => {
    render(<TaskFinder />)
    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: 'RELEASE' } })
    expect(screen.getByText('Ship release')).toBeTruthy()
    expect(screen.queryByText('Write docs')).toBeNull()
  })

  it('filters entity rows by a selected direct relationship', () => {
    render(<TaskFinder />)
    fireEvent.change(screen.getByLabelText('Filter tasks by related to item'), { target: { value: 'Decision · Keep it local' } })
    expect(screen.getByText('Ship release')).toBeTruthy()
    expect(screen.queryByText('Write docs')).toBeNull()
  })

  it('filters attachments by their host item', () => {
    render(<AttachmentFinder />)
    fireEvent.change(screen.getByLabelText('Filter comments by attached to item'), { target: { value: 'Task · Ship release' } })
    expect(screen.getByText('Ready to ship')).toBeTruthy()
    expect(screen.queryByText('Draft first')).toBeNull()
  })
})
