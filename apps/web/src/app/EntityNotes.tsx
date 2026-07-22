import { useState } from 'react'
import { api, Comment, Link } from '../api/client'

/** Phase 22 (D56): notes + links on ANY entity the backend allows.
 *
 *  Comment/Link have been polymorphic since Phase 4b — the API accepts all ten
 *  REF_ENTITY_TYPES — but the UI only ever created them on the project (and
 *  comments on tasks). This is the one component that closes that gap, so the
 *  behaviour can never drift per entity type.
 *
 *  It reads from the project-wide arrays PlanningPanel already loads and
 *  filters locally: expanding a row costs no request, and N open rows cost no
 *  N fetches. Writes go through the API and are pushed back into that shared
 *  state, so the Comments/Links tabs stay in sync without a refetch.
 *
 *  ponytail: links have no delete — `Link` is append-only by design (the API
 *  exposes only GET + POST). Not worked around here; add a slice if wanted.
 */
export function EntityNotes({
  projectId, entityType, entityId, comments, setComments, links, setLinks, label,
}: {
  projectId: string
  entityType: string
  entityId: string
  comments: Comment[]
  setComments: React.Dispatch<React.SetStateAction<Comment[]>>
  links: Link[]
  setLinks: React.Dispatch<React.SetStateAction<Link[]>>
  /** Human name of the host entity — used for accessible control labels. */
  label: string
}) {
  const [noteBody, setNoteBody] = useState('')
  const [linkUrl, setLinkUrl] = useState('')
  const [linkTitle, setLinkTitle] = useState('')
  const [showLink, setShowLink] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mine = (e: { entity_type: string; entity_id: string }) =>
    e.entity_type === entityType && e.entity_id === entityId
  const myNotes = comments.filter(mine)
  const myLinks = links.filter(mine)

  async function addNote(e: React.FormEvent) {
    e.preventDefault()
    const body = noteBody.trim()
    if (!body) return
    setSaving(true); setError(null)
    try {
      const c = await api.comments.create(projectId, { entity_type: entityType, entity_id: entityId, body })
      setComments(prev => [...prev, c])
      setNoteBody('')
    } catch {
      setError('Could not save the note.')
    } finally {
      setSaving(false)
    }
  }

  async function addLink(e: React.FormEvent) {
    e.preventDefault()
    const url = linkUrl.trim()
    if (!url) return
    setSaving(true); setError(null)
    try {
      const l = await api.links.create(projectId, {
        entity_type: entityType, entity_id: entityId, url,
        title: linkTitle.trim() || undefined,
      })
      setLinks(prev => [...prev, l])
      setLinkUrl(''); setLinkTitle(''); setShowLink(false)
    } catch {
      setError('Could not save the link.')
    } finally {
      setSaving(false)
    }
  }

  const removeNote = (id: string) =>
    void api.comments.remove(id).then(() => setComments(prev => prev.filter(c => c.id !== id)))

  return (
    <div className="pp-attach">
      {myNotes.length > 0 && (
        <>
          <p className="pp-section-lbl">Notes</p>
          {myNotes.map(c => (
            <div key={c.id} className="pp-comment">
              <span className="pp-comment-body">{c.body}</span>
              <span className="pp-comment-meta">
                {c.author_display ?? c.author_type} · {c.created_at.slice(0, 10)}
              </span>
              <button type="button" className="btn btn-ghost btn-xs" aria-label={`Delete note on ${label}`}
                onClick={() => removeNote(c.id)}>×</button>
            </div>
          ))}
        </>
      )}

      {myLinks.length > 0 && (
        <>
          <p className="pp-section-lbl">Links</p>
          {myLinks.map(l => (
            <a key={l.id} className="pp-row-title pp-link pp-attach-link" href={l.url}
              target="_blank" rel="noopener noreferrer">{l.title || l.url}</a>
          ))}
        </>
      )}

      <form className="pp-comment-add" onSubmit={addNote}>
        <textarea className="input" placeholder="Add a note…" aria-label={`Add a note on ${label}`}
          value={noteBody} onChange={e => setNoteBody(e.target.value)} />
        <div className="pp-attach-actions">
          <button type="submit" className="btn btn-outline btn-sm" disabled={saving}>
            {saving ? 'Saving…' : 'Note'}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={showLink}
            onClick={() => setShowLink(v => !v)}>Link</button>
        </div>
      </form>

      {showLink && (
        <form className="pp-comment-add" onSubmit={addLink}>
          <input className="input" type="url" required placeholder="https://…"
            aria-label={`Link URL for ${label}`}
            value={linkUrl} onChange={e => setLinkUrl(e.target.value)} />
          <input className="input" placeholder="Title (optional)"
            aria-label={`Link title for ${label}`}
            value={linkTitle} onChange={e => setLinkTitle(e.target.value)} />
          <button type="submit" className="btn btn-outline btn-sm" disabled={saving}
            style={{ alignSelf: 'flex-start' }}>Save link</button>
        </form>
      )}

      {error && <p className="pp-attach-error">{error}</p>}
    </div>
  )
}
