import { createContext, useContext, useEffect, useState } from 'react'
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from 'react'
import {
  api,
  type ConnectionEntityType,
  type ConnectionRelationType,
  type EntityConnection,
  type EntityConnectionCreate,
} from '../api/client'

export type ConnectionTarget = {
  entityType: ConnectionEntityType
  id: string
  title: string
  meta: string
}

type ConnectionContextValue = {
  connections: EntityConnection[]
  setConnections: Dispatch<SetStateAction<EntityConnection[]>>
  targets: ConnectionTarget[]
}

const ConnectionContext = createContext<ConnectionContextValue | null>(null)

export function ConnectionProvider({
  children,
  connections,
  setConnections,
  targets,
}: ConnectionContextValue & { children: ReactNode }) {
  // Endpoint deletes remove their connections transactionally in the API. The
  // root entity lists update locally at the same time, so prune those now-stale
  // records too instead of briefly showing an "Unavailable item" elsewhere.
  useEffect(() => {
    const available = new Set(targets.map(target => `${target.entityType}:${target.id}`))
    setConnections(previous => {
      const kept = previous.filter(connection =>
        available.has(`${connection.source_entity_type}:${connection.source_entity_id}`)
        && available.has(`${connection.target_entity_type}:${connection.target_entity_id}`),
      )
      return kept.length === previous.length ? previous : kept
    })
  }, [setConnections, targets])

  return (
    <ConnectionContext.Provider value={{ connections, setConnections, targets }}>
      {children}
    </ConnectionContext.Provider>
  )
}

/** Shared project-wide collection for detail views and Planning-level discovery. */
export function useConnectionContext() {
  return useContext(ConnectionContext)
}

const entityLabel: Record<ConnectionEntityType, string> = {
  phase: 'Phase',
  task: 'Task',
  decision: 'Decision',
  risk: 'Risk',
  milestone: 'Milestone',
  doc: 'Document',
}

type ComposerChoice = {
  key: string
  label: string
  relationType: ConnectionRelationType
  targetTypes: ConnectionEntityType[]
  /** The visible item is the canonical target for reverse-form actions. */
  currentIsTarget?: boolean
}

const allTargetTypes: ConnectionEntityType[] = ['phase', 'task', 'decision', 'risk', 'milestone', 'doc']

const choicesFor: Partial<Record<ConnectionEntityType, ComposerChoice[]>> = {
  task: [
    { key: 'depends_on', label: 'Depends on', relationType: 'depends_on', targetTypes: ['task'] },
    { key: 'implements', label: 'Implements', relationType: 'implements', targetTypes: ['decision'] },
    { key: 'mitigates', label: 'Mitigates', relationType: 'mitigates', targetTypes: ['risk'] },
    { key: 'contributes_to', label: 'Contributes to', relationType: 'contributes_to', targetTypes: ['milestone'] },
    { key: 'references', label: 'References', relationType: 'references', targetTypes: ['doc'] },
    { key: 'related_to', label: 'Related to', relationType: 'related_to', targetTypes: allTargetTypes },
  ],
  decision: [
    { key: 'implemented_by', label: 'Implemented by', relationType: 'implements', targetTypes: ['task'], currentIsTarget: true },
    { key: 'references', label: 'References', relationType: 'references', targetTypes: ['doc'] },
    { key: 'related_to', label: 'Related to', relationType: 'related_to', targetTypes: allTargetTypes },
  ],
  risk: [
    { key: 'mitigated_by', label: 'Mitigated by', relationType: 'mitigates', targetTypes: ['task'], currentIsTarget: true },
    { key: 'references', label: 'References', relationType: 'references', targetTypes: ['doc'] },
    { key: 'related_to', label: 'Related to', relationType: 'related_to', targetTypes: allTargetTypes },
  ],
  milestone: [
    { key: 'progress_from', label: 'Progress from', relationType: 'contributes_to', targetTypes: ['task'], currentIsTarget: true },
    { key: 'references', label: 'References', relationType: 'references', targetTypes: ['doc'] },
    { key: 'related_to', label: 'Related to', relationType: 'related_to', targetTypes: allTargetTypes },
  ],
}

const sourceLabels: Record<ConnectionRelationType, string> = {
  depends_on: 'Depends on',
  implements: 'Implements',
  mitigates: 'Mitigates',
  contributes_to: 'Contributes to',
  references: 'References',
  related_to: 'Related to',
}

const targetLabels: Record<ConnectionRelationType, string> = {
  depends_on: 'Required by',
  implements: 'Implemented by',
  mitigates: 'Mitigated by',
  contributes_to: 'Progress from',
  references: 'Referenced by',
  related_to: 'Related to',
}

function isEndpoint(connection: EntityConnection, entityType: ConnectionEntityType, entityId: string) {
  return (
    (connection.source_entity_type === entityType && connection.source_entity_id === entityId)
    || (connection.target_entity_type === entityType && connection.target_entity_id === entityId)
  )
}

/** Small scan signal for collapsed Planning rows; no controls are duplicated there. */
export function ConnectionCount({ entityType, entityId, label }: {
  entityType: ConnectionEntityType
  entityId: string
  label: string
}) {
  const ctx = useConnectionContext()
  if (!ctx) return null
  const count = ctx.connections.filter(connection => isEndpoint(connection, entityType, entityId)).length
  if (!count) return null
  const noun = count === 1 ? 'connection' : 'connections'
  return <span className="pp-connection-count" aria-label={`${count} ${noun}; open ${label} details`}>{count}</span>
}

type DisplayConnection = {
  connection: EntityConnection
  label: string
  target: ConnectionTarget | undefined
}

function displayConnections(
  connections: EntityConnection[],
  targets: ConnectionTarget[],
  entityType: ConnectionEntityType,
  entityId: string,
): DisplayConnection[] {
  return connections
    .filter(connection => isEndpoint(connection, entityType, entityId))
    .map(connection => {
      const currentIsSource = connection.source_entity_type === entityType && connection.source_entity_id === entityId
      const otherType = currentIsSource ? connection.target_entity_type : connection.source_entity_type
      const otherId = currentIsSource ? connection.target_entity_id : connection.source_entity_id
      return {
        connection,
        label: currentIsSource ? sourceLabels[connection.relation_type] : targetLabels[connection.relation_type],
        target: targets.find(target => target.entityType === otherType && target.id === otherId),
      }
    })
}

export function EntityConnections({
  projectId,
  entityType,
  entityId,
  label,
}: {
  projectId: string
  entityType: ConnectionEntityType
  entityId: string
  label: string
}) {
  const ctx = useConnectionContext()
  const choices = choicesFor[entityType] ?? []
  const [composerOpen, setComposerOpen] = useState(false)
  const [choiceKey, setChoiceKey] = useState(choices[0]?.key ?? '')
  const [targetKey, setTargetKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!ctx || choices.length === 0) return null
  const connectionContext = ctx

  const shown = displayConnections(connectionContext.connections, connectionContext.targets, entityType, entityId)
  const groups = shown.reduce<Map<string, DisplayConnection[]>>((grouped, item) => {
    grouped.set(item.label, [...(grouped.get(item.label) ?? []), item])
    return grouped
  }, new Map())
  const choice = choices.find(item => item.key === choiceKey) ?? choices[0]
  const candidates = connectionContext.targets.filter(target =>
    choice.targetTypes.includes(target.entityType)
    && !(target.entityType === entityType && target.id === entityId),
  )
  const selectedTarget = candidates.find(target => `${target.entityType}:${target.id}` === targetKey)

  function openComposer() {
    setChoiceKey(choices[0].key)
    setTargetKey('')
    setError(null)
    setComposerOpen(true)
  }

  function closeComposer() {
    setComposerOpen(false)
    setTargetKey('')
    setError(null)
  }

  async function createConnection(event: FormEvent) {
    event.preventDefault()
    if (!selectedTarget) {
      setError('Choose an item to connect.')
      return
    }
    const current = { entityType, id: entityId }
    const source = choice.currentIsTarget ? selectedTarget : current
    const target = choice.currentIsTarget ? current : selectedTarget
    const payload: EntityConnectionCreate = {
      relation_type: choice.relationType,
      source_entity_type: source.entityType,
      source_entity_id: source.id,
      target_entity_type: target.entityType,
      target_entity_id: target.id,
    }
    setSaving(true)
    setError(null)
    try {
      const created = await api.connections.create(projectId, payload)
      connectionContext.setConnections(previous => [...previous, created])
      closeComposer()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not add this connection.')
    } finally {
      setSaving(false)
    }
  }

  async function removeConnection(connection: EntityConnection) {
    setRemovingId(connection.id)
    setError(null)
    try {
      await api.connections.remove(connection.id)
      connectionContext.setConnections(previous => previous.filter(item => item.id !== connection.id))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not remove this connection.')
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <section className="pp-connections" aria-label={`Connections for ${label}`}>
      <div className="pp-connections-head">
        <h4>Connections{shown.length ? ` · ${shown.length}` : ''}</h4>
        {!composerOpen && <button type="button" className="btn btn-outline btn-sm" onClick={openComposer}>Add connection</button>}
      </div>

      {shown.length === 0 ? <p className="pp-connections-empty">No connections yet.</p> : (
        <div className="pp-connection-groups">
          {[...groups.entries()].map(([groupLabel, items]) => (
            <div className="pp-connection-group" key={groupLabel}>
              <p className="pp-connection-group-label">{groupLabel}</p>
              <ul className="pp-connection-list">
                {items.map(({ connection, target }) => (
                  <li className="pp-connection-item" key={connection.id}>
                    <div className="pp-connection-copy">
                      <span className="pp-connection-type">{entityLabel[target?.entityType ?? (connection.source_entity_type === entityType && connection.source_entity_id === entityId ? connection.target_entity_type : connection.source_entity_type)]}</span>
                      <span className="pp-connection-title">{target?.title ?? 'Unavailable item'}</span>
                      {target?.meta && <span className="pp-connection-meta">{target.meta}</span>}
                    </div>
                    <button type="button" className="pp-connection-remove" disabled={removingId === connection.id}
                      aria-label={`Remove connection to ${target?.title ?? 'unavailable item'}`}
                      onClick={() => void removeConnection(connection)}>
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {composerOpen && (
        <form className="pp-connection-composer" onSubmit={createConnection}>
          <label>
            <span>Relationship</span>
            <select className="input select input-sm" value={choice.key}
              aria-label={`Relationship for ${label}`}
              disabled={saving}
              onChange={event => { setChoiceKey(event.target.value); setTargetKey(''); setError(null) }}>
              {choices.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select>
          </label>
          <label>
            <span>Connect to</span>
            <select className="input select input-sm" value={targetKey}
              aria-label={`Connect ${label} to`}
              disabled={saving}
              onChange={event => { setTargetKey(event.target.value); setError(null) }}>
              <option value="">Choose an item…</option>
              {candidates.map(target => (
                <option key={`${target.entityType}:${target.id}`} value={`${target.entityType}:${target.id}`}>
                  {entityLabel[target.entityType]} · {target.title}{target.meta ? ` · ${target.meta}` : ''}
                </option>
              ))}
            </select>
          </label>
          <div className="pp-connection-actions">
            <button type="submit" className="btn btn-solid btn-sm" disabled={saving}>Add</button>
            <button type="button" className="btn btn-ghost btn-sm" disabled={saving} onClick={closeComposer}>Cancel</button>
          </div>
          {error && <p className="form-error pp-connection-error" role="alert">{error}</p>}
        </form>
      )}
      {!composerOpen && error && <p className="form-error pp-connection-error" role="alert">{error}</p>}
    </section>
  )
}
