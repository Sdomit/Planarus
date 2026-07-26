import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type NotificationItem } from '../api/client'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'

const POLL_MS = 60_000
const DESKTOP_KEY = 'ab-desktop-notifications'
const SEEN_KEY = 'ab-seen-notifications'

function desktopSupported(): boolean {
  return typeof Notification !== 'undefined'
}

// ponytail: unread state lives in localStorage, not the DB. The feed is derived
// from canonical state (see notification_service.py) — an open blocker stays in
// the list until it is actually resolved, so "seen" is a per-browser view
// concern, not a fact about the project. Feed ids are stable ({kind}:{entity_id}),
// which is what makes tracking them client-side reliable.
function loadSeen(): Set<string> {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(SEEN_KEY) ?? '[]')
    return new Set(Array.isArray(raw) ? raw.filter((v) => typeof v === 'string') : [])
  } catch {
    return new Set()
  }
}

/** Topbar bell: in-app notification feed + optional desktop notifications. */
export default function NotificationsBell({
  projectId,
  onOpenItem,
}: {
  projectId: string | null
  onOpenItem: (item: NotificationItem) => void
}) {
  const [items, setItems] = useState<NotificationItem[]>([])
  const [open, setOpen] = useState(false)
  const [seen, setSeen] = useState<Set<string>>(loadSeen)
  const [desktopOn, setDesktopOn] = useState(
    () => localStorage.getItem(DESKTOP_KEY) === 'true',
  )
  const knownIds = useRef<Set<string> | null>(null)
  const bellRef = useRef<HTMLButtonElement>(null)
  const desktopOnRef = useRef(desktopOn)
  desktopOnRef.current = desktopOn

  const refresh = useCallback(() => {
    api.notifications
      .feed(projectId)
      .then((feed) => {
        setItems(feed.items)
        const prev = knownIds.current
        const fresh =
          prev === null ? [] : feed.items.filter((i) => !prev.has(i.id))
        knownIds.current = new Set(feed.items.map((i) => i.id))
        if (
          fresh.length > 0 &&
          desktopOnRef.current &&
          desktopSupported() &&
          Notification.permission === 'granted'
        ) {
          const head = fresh[0]
          new Notification(`Planarus — ${head.project_title}`, {
            body:
              fresh.length === 1
                ? head.title
                : `${head.title} (+${fresh.length - 1} more)`,
            tag: 'planarus-feed', // replaces instead of stacking
          })
        }
      })
      .catch(() => {
        /* feed is best-effort; keep the last known items */
      })
  }, [projectId])

  useEffect(() => {
    knownIds.current = null
    refresh()
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    if (!open) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        bellRef.current?.focus()
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [open])

  const toggleDesktop = () => {
    if (desktopOn) {
      setDesktopOn(false)
      localStorage.setItem(DESKTOP_KEY, 'false')
      return
    }
    if (!desktopSupported()) return
    const enable = () => {
      setDesktopOn(true)
      localStorage.setItem(DESKTOP_KEY, 'true')
    }
    if (Notification.permission === 'granted') enable()
    else {
      Notification.requestPermission().then((perm) => {
        if (perm === 'granted') enable()
      })
    }
  }

  const unread = items.filter((i) => !seen.has(i.id))

  // Opening the panel is the "read" action. Only the ids currently in the feed
  // are stored, so the set self-prunes as items resolve — and an item that
  // resolves then recurs alerts again rather than staying silently seen.
  const toggleOpen = () => {
    if (!open) {
      const ids = items.map((i) => i.id)
      setSeen(new Set(ids))
      localStorage.setItem(SEEN_KEY, JSON.stringify(ids))
    }
    setOpen((v) => !v)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        ref={bellRef}
        className="ab-iconbtn"
        type="button"
        aria-label={`Notifications (${unread.length})`}
        aria-expanded={open}
        onClick={toggleOpen}
      >
        <Icon name="bell" className="ic-18" />
        {unread.length > 0 && (
          <span
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: 2,
              right: 2,
              minWidth: 16,
              height: 16,
              padding: '0 4px',
              borderRadius: 8,
              // The count is knocked out of a solid danger fill, so it inverts with the
              // theme: dark digits on the light dark-mode rose, white on the light-mode red.
              background: 'var(--status-danger-fg)',
              color: 'var(--bg-surface)',
              fontSize: 10,
              fontWeight: 700,
              lineHeight: '16px',
              textAlign: 'center',
            }}
          >
            {unread.length > 99 ? '99+' : unread.length}
          </span>
        )}
      </button>

      {open && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 30 }}
            aria-hidden="true"
            onClick={() => setOpen(false)}
          />
          <div
            className="card"
            role="dialog"
            aria-label="Notifications"
            style={{
              position: 'absolute',
              right: 0,
              top: 'calc(100% + 8px)',
              width: 360,
              maxWidth: '90vw',
              maxHeight: 420,
              overflowY: 'auto',
              zIndex: 31,
              padding: 'var(--space-4)',
              boxShadow: '0 8px 30px rgba(0,0,0,.25)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <strong style={{ flex: 1 }}>Notifications</strong>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={desktopOn}
                  onChange={toggleDesktop}
                  disabled={!desktopSupported()}
                />
                Desktop alerts
              </label>
            </div>
            {items.length === 0 ? (
              <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>
                All clear — nothing needs attention.
              </p>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="ab-notification-row"
                  onClick={() => {
                    setOpen(false)
                    onOpenItem(item)
                  }}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '8px 0',
                    background: 'transparent',
                    border: 0,
                    borderBottom: '1px solid var(--border-subtle, rgba(128,128,128,.15))',
                    color: 'inherit',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                    <StatusBadge kind="notifseverity" value={item.severity} />
                    <span style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                      {item.title}
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>
                    {item.project_title}
                    {item.detail ? ` · ${item.detail}` : ''}
                  </div>
                </button>
              ))
            )}
          </div>
        </>
      )}
    </div>
  )
}
