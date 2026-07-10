import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type NotificationItem } from '../api/client'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'

const POLL_MS = 60_000
const DESKTOP_KEY = 'ab-desktop-notifications'

function desktopSupported(): boolean {
  return typeof Notification !== 'undefined'
}

/** Topbar bell: in-app notification feed + optional desktop notifications. */
export default function NotificationsBell({ projectId }: { projectId: string | null }) {
  const [items, setItems] = useState<NotificationItem[]>([])
  const [open, setOpen] = useState(false)
  const [desktopOn, setDesktopOn] = useState(
    () => localStorage.getItem(DESKTOP_KEY) === 'true',
  )
  const knownIds = useRef<Set<string> | null>(null)
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
          new Notification(`AgentBoard — ${head.project_title}`, {
            body:
              fresh.length === 1
                ? head.title
                : `${head.title} (+${fresh.length - 1} more)`,
            tag: 'agentboard-feed', // replaces instead of stacking
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

  return (
    <div style={{ position: 'relative' }}>
      <button
        className="ab-iconbtn"
        type="button"
        aria-label={`Notifications (${items.length})`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" className="ic-18" />
        {items.length > 0 && (
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
              background: 'var(--danger, #d9432b)',
              color: '#fff',
              fontSize: 10,
              fontWeight: 700,
              lineHeight: '16px',
              textAlign: 'center',
            }}
          >
            {items.length > 99 ? '99+' : items.length}
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
                <div
                  key={item.id}
                  style={{
                    padding: '8px 0',
                    borderBottom: '1px solid var(--border-subtle, rgba(128,128,128,.15))',
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
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  )
}
