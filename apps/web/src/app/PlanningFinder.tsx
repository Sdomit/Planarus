import { useMemo, useState } from 'react'
import type { ConnectionEntityType } from '../api/client'
import { useConnectionContext } from './EntityConnections'

type ItemWithId = { id: string }
type AttachmentHost = { entity_type: string; entity_id: string }

type FinderOption = {
  key: string
  label: string
}

const entityLabels: Record<string, string> = {
  phase: 'Phase',
  task: 'Task',
  decision: 'Decision',
  risk: 'Risk',
  milestone: 'Milestone',
  doc: 'Document',
  project: 'Project',
}

const keyFor = (entityType: string, id: string) => `${entityType}:${id}`

/** Case-insensitive text match kept deliberately small and predictable. */
export function matchesFinderText(searchText: string, query: string): boolean {
  return searchText.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
}

function sortOptions(options: FinderOption[]): FinderOption[] {
  return [...options].sort((left, right) => left.label.localeCompare(right.label, undefined, { sensitivity: 'base' }))
}

/**
 * One consistent finder for Planning collections. Entity tabs use the typed
 * connection spine; attachment tabs use the entity that owns the comment/link.
 * The native datalist keeps a large related-item picker searchable without a
 * second popover or a separate submit action.
 */
export function usePlanningFinder<T extends ItemWithId>({
  label,
  items,
  searchText,
  entityType,
  attachmentHost,
}: {
  label: string
  items: T[]
  searchText: (item: T) => string
  entityType?: ConnectionEntityType
  attachmentHost?: (item: T) => AttachmentHost
}) {
  const connectionContext = useConnectionContext()
  const [query, setQuery] = useState('')
  const [relatedText, setRelatedText] = useState('')
  const [relatedKey, setRelatedKey] = useState<string | null>(null)
  const inputId = `planning-finder-${label.toLocaleLowerCase().replace(/[^a-z0-9]+/g, '-')}`

  const options = useMemo(() => {
    if (!connectionContext) return []
    const targetByKey = new Map(connectionContext.targets.map(target => [keyFor(target.entityType, target.id), target]))
    const optionByKey = new Map<string, FinderOption>()

    if (entityType) {
      const itemIds = new Set(items.map(item => item.id))
      for (const connection of connectionContext.connections) {
        const sourceIsShown = connection.source_entity_type === entityType && itemIds.has(connection.source_entity_id)
        const targetIsShown = connection.target_entity_type === entityType && itemIds.has(connection.target_entity_id)
        if (!sourceIsShown && !targetIsShown) continue
        const otherKey = sourceIsShown
          ? keyFor(connection.target_entity_type, connection.target_entity_id)
          : keyFor(connection.source_entity_type, connection.source_entity_id)
        const target = targetByKey.get(otherKey)
        if (target) optionByKey.set(otherKey, { key: otherKey, label: `${entityLabels[target.entityType]} · ${target.title}` })
      }
    } else if (attachmentHost) {
      for (const item of items) {
        const host = attachmentHost(item)
        const hostKey = keyFor(host.entity_type, host.entity_id)
        const target = targetByKey.get(hostKey)
        const hostLabel = target ? `${entityLabels[target.entityType]} · ${target.title}` : entityLabels[host.entity_type] ?? host.entity_type
        optionByKey.set(hostKey, { key: hostKey, label: hostLabel })
      }
    }

    return sortOptions([...optionByKey.values()])
  }, [attachmentHost, connectionContext, entityType, items])

  const filtered = useMemo(() => items.filter(item => {
    if (query.trim() && !matchesFinderText(searchText(item), query)) return false
    if (!relatedKey) return true

    if (entityType && connectionContext) {
      const itemKey = keyFor(entityType, item.id)
      return connectionContext.connections.some(connection =>
        (keyFor(connection.source_entity_type, connection.source_entity_id) === itemKey
          && keyFor(connection.target_entity_type, connection.target_entity_id) === relatedKey)
        || (keyFor(connection.target_entity_type, connection.target_entity_id) === itemKey
          && keyFor(connection.source_entity_type, connection.source_entity_id) === relatedKey),
      )
    }

    return attachmentHost ? keyFor(attachmentHost(item).entity_type, attachmentHost(item).entity_id) === relatedKey : true
  }), [attachmentHost, connectionContext, entityType, items, query, relatedKey, searchText])

  const hasFilter = Boolean(query.trim() || relatedKey)
  const relationshipLabel = entityType ? 'Related to' : 'Attached to'

  const controls = (
    <div className="pp-finder" role="search" aria-label={`${label} finder`}>
      <input
        className="input input-sm pp-finder-search"
        type="search"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder={`Search ${label}…`}
        aria-label={`Search ${label}`}
      />
      {options.length > 0 && (
        <>
          <input
            className="input input-sm pp-finder-related"
            list={`${inputId}-related`}
            value={relatedText}
            onChange={event => {
              const next = event.target.value
              const option = options.find(candidate => candidate.label === next)
              setRelatedText(next)
              setRelatedKey(option?.key ?? null)
            }}
            placeholder={`${relationshipLabel}…`}
            aria-label={`Filter ${label} by ${relationshipLabel.toLocaleLowerCase()} item`}
          />
          <datalist id={`${inputId}-related`}>
            {options.map(option => <option key={option.key} value={option.label} />)}
          </datalist>
        </>
      )}
      {hasFilter && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setQuery(''); setRelatedText(''); setRelatedKey(null) }}>
          Clear
        </button>
      )}
      <span className="pp-finder-count" aria-live="polite">{filtered.length} of {items.length}</span>
    </div>
  )

  return { controls, filtered, hasFilter }
}
