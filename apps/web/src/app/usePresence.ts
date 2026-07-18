import { useEffect, useRef, useState } from 'react'
import { api, type PresenceEntry } from '../api/client'

const BEAT_MS = 10_000 // server TTL is 30s — three missed beats release the lock

export interface PresenceState {
  /** someone ELSE holds the edit lock — drop this surface to read-only */
  lockedByOther: boolean
  editorName: string | null
  entries: PresenceEntry[]
  /** false until a beat succeeds; stays false in local mode (surface 404s) */
  active: boolean
}

/**
 * P11.2 (D27): polling-heartbeat presence + advisory soft-lock for one doc.
 *
 * Dormant by design outside team mode: the first beat 404s (auth off) or 401s
 * (no session yet — sign-in UI lands in P11.3) and the hook stops polling until
 * remount. Hidden tabs skip beats so the server TTL releases their lock.
 */
export function usePresence(docId: string, editing: boolean): PresenceState {
  const [view, setView] = useState<import('../api/client').PresenceView | null>(null)
  const deadRef = useRef(false)

  useEffect(() => {
    deadRef.current = false
    let stopped = false
    let everActive = false // only send leave() if a beat ever landed
    let timer: number | undefined

    const beat = async () => {
      if (stopped || deadRef.current) return
      if (timer) { clearTimeout(timer); timer = undefined }
      if (!document.hidden) {
        try {
          const v = await api.docs.presenceBeat(docId, editing ? 'editing' : 'viewing')
          everActive = true
          if (!stopped) setView(v)
        } catch (e) {
          const msg = e instanceof Error ? e.message : ''
          if (msg.startsWith('404') || msg.startsWith('401')) {
            deadRef.current = true // local mode / signed out: go dormant
            if (!stopped) setView(null)
            return
          }
          // transient failure: keep the loop alive, retry next tick
        }
      }
      if (!stopped) timer = window.setTimeout(() => void beat(), BEAT_MS)
    }

    const onVisibility = () => { if (!document.hidden) void beat() }
    void beat()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      if (everActive && !deadRef.current) void api.docs.presenceLeave(docId).catch(() => { /* best effort */ })
    }
  }, [docId, editing])

  const you = view?.you ?? null
  const editorId = view?.editor_user_id ?? null
  const lockedByOther = !!(editorId && you && editorId !== you)
  return {
    lockedByOther,
    editorName: lockedByOther
      ? (view?.entries.find((e) => e.user_id === editorId)?.display_name ?? 'Someone')
      : null,
    entries: view?.entries ?? [],
    active: view != null,
  }
}
