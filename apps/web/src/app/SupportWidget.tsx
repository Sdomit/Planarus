import { useEffect, useRef, useState } from 'react'
import { Icon } from './Icon'

// A "landing soon" support bubble. Real AI support isn't wired yet, so the first
// message the visitor sends just surfaces the author's links and locks the thread.
const LINKS = [
  { label: 'LinkedIn', href: 'https://www.linkedin.com/in/sarmad-domit/' },
  { label: 'GitHub', href: 'https://github.com/Sdomit' },
  { label: 'Website', href: 'https://www.sarmaddomit.com' },
]
const GREETING = '👋 Hi! Local AI support is landing soon.'
const REPLY = "Thanks for reaching out! Support isn't live yet — meanwhile, check out my links:"

function Bubble({ from, children }: { from: 'bot' | 'user'; children: React.ReactNode }) {
  const isUser = from === 'user'
  return (
    <div style={{
      alignSelf: isUser ? 'flex-end' : 'flex-start',
      maxWidth: '85%',
      padding: 'var(--space-2) var(--space-3)',
      borderRadius: 'var(--radius-lg)',
      background: isUser ? 'var(--accent)' : 'var(--bg-subtle)',
      color: isUser ? 'var(--text-inverse)' : 'var(--text-primary)',
      fontSize: 'var(--text-sm)',
      lineHeight: 'var(--leading-relaxed)',
    }}>
      {children}
    </div>
  )
}

export default function SupportWidget() {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [userMsg, setUserMsg] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const locked = userMsg !== null

  useEffect(() => {
    if (!open) return
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [open])

  useEffect(() => { if (open && !locked) inputRef.current?.focus() }, [open, locked])

  const send = () => {
    const text = draft.trim()
    if (!text || locked) return // any non-empty message locks the thread
    setUserMsg(text)
    setDraft('')
  }

  return (
    <>
      {open && (
        <div style={panelStyle} role="dialog" aria-label="AI support chat">
          <div style={headerStyle}>
            <Icon name="message" className="ic-14" />
            <span style={{ fontWeight: 600 }}>AI Support</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close support chat"
              style={closeStyle}
            >
              <Icon name="x" className="ic-14" />
            </button>
          </div>

          <div style={bodyStyle}>
            <Bubble from="bot">{GREETING}</Bubble>
            {locked && <Bubble from="user">{userMsg}</Bubble>}
            {locked && (
              <Bubble from="bot">
                {REPLY}
                <div style={linksRowStyle}>
                  {LINKS.map((l) => (
                    <a key={l.label} href={l.href} target="_blank" rel="noopener noreferrer" style={chipStyle}>
                      {l.label}
                      <Icon name="external" className="ic-14" />
                    </a>
                  ))}
                </div>
              </Bubble>
            )}
          </div>

          <div style={footerStyle}>
            <input
              ref={inputRef}
              type="text"
              value={draft}
              disabled={locked}
              placeholder={locked ? 'Support is not live yet' : 'Type a message…'}
              aria-label="Message support"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send() }}
              style={inputStyle}
            />
            <button
              type="button"
              className="btn btn-solid btn-sm"
              disabled={locked || !draft.trim()}
              onClick={send}
            >
              Send
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close support chat' : 'Open support chat'}
        aria-expanded={open}
        style={fabStyle}
      >
        <Icon name={open ? 'x' : 'message'} className="ic-20" />
      </button>
    </>
  )
}

// --z-overlay (300): floats above page content but under modals, so an open
// dialog's controls are never covered by the bubble.
const fabStyle: React.CSSProperties = {
  position: 'fixed', right: 20, bottom: 20, zIndex: 300,
  width: 52, height: 52, borderRadius: '50%',
  background: 'var(--accent)', color: 'var(--text-inverse)',
  border: 'none', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  boxShadow: 'var(--shadow-lg)',
}
const panelStyle: React.CSSProperties = {
  position: 'fixed', right: 20, bottom: 84, zIndex: 300,
  width: 'min(340px, calc(100vw - 40px))', maxHeight: 'min(70vh, 520px)',
  display: 'flex', flexDirection: 'column',
  background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden',
}
const headerStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
  padding: 'var(--space-3) var(--space-4)',
  borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-primary)',
}
const closeStyle: React.CSSProperties = {
  marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer',
  color: 'var(--text-secondary)', display: 'inline-flex', padding: 4, borderRadius: 6,
}
const bodyStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
  padding: 'var(--space-4)', overflowY: 'auto', flex: 1,
}
const footerStyle: React.CSSProperties = {
  display: 'flex', gap: 'var(--space-2)', padding: 'var(--space-3)',
  borderTop: '1px solid var(--border-subtle)',
}
const inputStyle: React.CSSProperties = {
  flex: 1, minWidth: 0, padding: 'var(--space-2) var(--space-3)',
  border: '1px solid var(--border-default)', borderRadius: 6,
  background: 'var(--bg-canvas)', color: 'var(--text-primary)', fontSize: 'var(--text-sm)',
}
const linksRowStyle: React.CSSProperties = {
  display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', marginTop: 'var(--space-2)',
}
const chipStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 10px',
  borderRadius: 'var(--radius-lg)', background: 'var(--bg-surface)',
  border: '1px solid var(--border-default)', color: 'var(--text-accent)',
  fontSize: 'var(--text-sm)', fontWeight: 500, textDecoration: 'none',
}
