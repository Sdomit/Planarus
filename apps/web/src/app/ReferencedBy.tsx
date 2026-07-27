import { useEffect, useState } from 'react'
import { api, type Mention } from '../api/client'

interface ReferencedByProps {
  projectId: string
  entityType: string
  entityId: string
  /** Called with a source doc's id when a backlink row is clicked, to open it. */
  onOpenDoc?: (docId: string) => void
}

/**
 * "Referenced by" panel (#138/plan 23) — the read side of a doc @mention.
 * Mounted next to Attachments/EntityConnections on any mentionable entity's
 * detail view. Renders nothing while empty, so it adds no visual weight to
 * entities nobody has mentioned yet.
 */
export function ReferencedBy({ projectId, entityType, entityId, onOpenDoc }: ReferencedByProps) {
  const [mentions, setMentions] = useState<Mention[]>([])

  useEffect(() => {
    let cancelled = false
    api.mentions.list(projectId, { target_type: entityType, target_id: entityId })
      .then(rows => { if (!cancelled) setMentions(rows) })
      // Supplementary panel: a failed fetch just stays empty rather than
      // taking the host detail view down with it.
      .catch(() => {})
    return () => { cancelled = true }
  }, [projectId, entityType, entityId])

  if (mentions.length === 0) return null

  return (
    <div className="pp-attach">
      <p className="pp-section-lbl">Referenced by</p>
      {mentions.map(m => (
        <div key={m.id} className="pp-comment">
          {onOpenDoc ? (
            <span className="pp-row-title pp-link" role="button" tabIndex={0}
              onClick={() => onOpenDoc(m.source_doc_id)}
              onKeyDown={e => e.key === 'Enter' && onOpenDoc(m.source_doc_id)}>
              {m.source_doc_title ?? '(deleted doc)'}
            </span>
          ) : (
            <span className="pp-row-title">{m.source_doc_title ?? '(deleted doc)'}</span>
          )}
        </div>
      ))}
    </div>
  )
}
