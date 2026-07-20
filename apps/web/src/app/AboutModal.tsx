import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

// Author + build details. The version comes from the API rather than a constant
// here so it can never drift from what the running server actually reports.
const AUTHOR = [
  { label: 'Website', href: 'https://www.sarmaddomit.com', text: 'www.sarmaddomit.com' },
  { label: 'GitHub', href: 'https://github.com/Sdomit', text: 'github.com/Sdomit' },
  { label: 'Email', href: 'mailto:sarmad.domit@gmail.com', text: 'sarmad.domit@gmail.com' },
]

const rowStyle: React.CSSProperties = {
  display: 'flex', gap: 'var(--space-3)', padding: '5px 0', fontSize: 'var(--text-sm)',
}
const keyStyle: React.CSSProperties = {
  width: 76, flexShrink: 0, color: 'var(--text-tertiary)',
}
const headingStyle: React.CSSProperties = {
  margin: 'var(--space-4) 0 var(--space-1)', fontSize: 'var(--text-xs)',
  textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-tertiary)',
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={rowStyle}>
      <span style={keyStyle}>{label}</span>
      <span style={{ minWidth: 0, wordBreak: 'break-word' }}>{children}</span>
    </div>
  )
}

function Ext({ href, text }: { href: string; text: string }) {
  // noreferrer alongside noopener: these are the author's own links, but the
  // rule holds for every target=_blank we ship.
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-accent)' }}>
      {text}
    </a>
  )
}

export default function AboutModal({ onClose }: { onClose: () => void }) {
  const [version, setVersion] = useState<string | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])

  useEffect(() => {
    api.info.get().then((i) => setVersion(i.version)).catch(() => setVersion('unknown'))
  }, [])

  return (
    <div className="modal-overlay">
      <div className="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="about-title">
        <div className="modal-header">
          <span className="modal-title" id="about-title">About Approvo</span>
        </div>
        <div className="modal-body">
          <p style={{ marginTop: 0 }}>
            A local-first AI project cockpit — planning, context packs and approval-gated
            agent access, stored in folders you own.
          </p>

          <div style={headingStyle}>Application</div>
          <Row label="Version">{version ?? '…'}</Row>
          <Row label="Source">
            <Ext href="https://github.com/Sdomit/AgentBoard" text="github.com/Sdomit/AgentBoard" />
          </Row>
          <Row label="License">Apache-2.0</Row>

          <div style={headingStyle}>Author</div>
          <Row label="Name">Sarmad Domit</Row>
          {AUTHOR.map((l) => (
            <Row key={l.label} label={l.label}><Ext href={l.href} text={l.text} /></Row>
          ))}
        </div>
        <div className="modal-footer">
          <button ref={closeRef} type="button" className="btn btn-solid btn-sm" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
