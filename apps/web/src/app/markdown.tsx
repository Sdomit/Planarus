import type { CSSProperties, JSX, ReactNode } from 'react'

// ponytail: a small renderer for the Markdown subset Approvo itself
// generates (headings, lists, tables, fenced code, quotes, inline marks,
// links) — everything is emitted as React elements, never raw HTML, so user
// content can't inject markup. Upgrade to a real parser lib if authors need
// footnotes/images/raw HTML.

const SAFE_HREF = /^(https?:|mailto:|#|\.{0,2}\/)/i
const INLINE_RE =
  /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(~~[^~]+~~)|(\[[^\]]+\]\([^)\s]+\))/g

export function parseInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let key = 0
  for (const m of text.matchAll(INLINE_RE)) {
    const idx = m.index ?? 0
    if (idx > last) nodes.push(text.slice(last, idx))
    const tok = m[0]
    if (m[1]) nodes.push(<code key={key++}>{tok.slice(1, -1)}</code>)
    else if (m[2]) nodes.push(<strong key={key++}>{parseInline(tok.slice(2, -2))}</strong>)
    else if (m[3]) nodes.push(<em key={key++}>{parseInline(tok.slice(1, -1))}</em>)
    else if (m[4]) nodes.push(<s key={key++}>{parseInline(tok.slice(2, -2))}</s>)
    else if (m[5]) {
      const inner = tok.slice(1, -1) // strip [ … )
      const split = inner.indexOf('](')
      const label = inner.slice(0, split)
      const href = inner.slice(split + 2)
      if (SAFE_HREF.test(href)) {
        nodes.push(
          <a key={key++} href={href} target="_blank" rel="noreferrer noopener">
            {parseInline(label)}
          </a>,
        )
      } else {
        nodes.push(label) // unsafe scheme → text only
      }
    }
    last = idx + tok.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

interface Li {
  indent: number
  ordered: boolean
  text: string
}

function renderList(items: Li[], from: number, level: number, key: number): [ReactNode, number] {
  const children: ReactNode[] = []
  const ordered = items[from].ordered
  let i = from
  while (i < items.length && items[i].indent >= level) {
    if (items[i].indent > level) {
      const [nested, next] = renderList(items, i, items[i].indent, key)
      children.push(<li key={`n${i}`} className="md-nest">{nested}</li>)
      i = next
    } else {
      children.push(<li key={i}>{parseInline(items[i].text)}</li>)
      i += 1
    }
  }
  const list = ordered ? <ol key={`l${key}-${from}`}>{children}</ol> : <ul key={`l${key}-${from}`}>{children}</ul>
  return [list, i]
}

const CELL_STYLE: CSSProperties = {
  border: '1px solid var(--border-subtle, #ccc)',
  padding: '4px 8px',
  textAlign: 'left',
}

export function renderMarkdown(md: string): ReactNode[] {
  const out: ReactNode[] = []
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  let i = 0
  let key = 0

  // YAML frontmatter → dim metadata block.
  if (lines[0]?.trim() === '---') {
    const end = lines.findIndex((l, idx) => idx > 0 && l.trim() === '---')
    if (end > 0) {
      out.push(
        <pre key={key++} className="md-frontmatter" style={{ opacity: 0.65, fontSize: '0.85em' }}>
          {lines.slice(1, end).join('\n')}
        </pre>,
      )
      i = end + 1
    }
  }

  let para: string[] = []
  const flushPara = () => {
    if (para.length) {
      out.push(<p key={key++}>{parseInline(para.join(' '))}</p>)
      para = []
    }
  }

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (trimmed === '') {
      flushPara()
      i += 1
      continue
    }

    const fence = trimmed.match(/^```(\S*)/)
    if (fence) {
      flushPara()
      const buf: string[] = []
      i += 1
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        buf.push(lines[i])
        i += 1
      }
      i += 1 // closing fence
      out.push(
        <pre key={key++} className="md-code">
          <code data-lang={fence[1] || undefined}>{buf.join('\n')}</code>
        </pre>,
      )
      continue
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      flushPara()
      const Tag = `h${heading[1].length}` as keyof JSX.IntrinsicElements // React 19: JSX namespace imported, not global
      out.push(<Tag key={key++}>{parseInline(heading[2])}</Tag>)
      i += 1
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushPara()
      out.push(<hr key={key++} />)
      i += 1
      continue
    }

    if (trimmed.startsWith('>')) {
      flushPara()
      const buf: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        buf.push(lines[i].trim().replace(/^>\s?/, ''))
        i += 1
      }
      out.push(
        <blockquote key={key++}>
          {buf.map((l, j) => (
            <p key={j} style={{ margin: '0.25em 0' }}>{parseInline(l)}</p>
          ))}
        </blockquote>,
      )
      continue
    }

    // Table: header row + separator row of dashes.
    if (
      trimmed.startsWith('|') &&
      i + 1 < lines.length &&
      /^\|?[\s:|-]+\|?$/.test(lines[i + 1].trim()) &&
      lines[i + 1].includes('-')
    ) {
      flushPara()
      const cells = (l: string) =>
        l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
      const header = cells(lines[i])
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(cells(lines[i]))
        i += 1
      }
      out.push(
        <div key={key++} style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', margin: '0.5em 0' }}>
            <thead>
              <tr>
                {header.map((h, j) => (
                  <th key={j} style={CELL_STYLE}>{parseInline(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci} style={CELL_STYLE}>{parseInline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    const li = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/)
    if (li) {
      flushPara()
      const items: Li[] = []
      while (i < lines.length) {
        const m = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/)
        if (!m) break
        items.push({
          indent: Math.floor(m[1].length / 2),
          ordered: /\d/.test(m[2]),
          text: m[3],
        })
        i += 1
      }
      // Start at the shallowest indent in the block — starting at items[0]'s
      // indent would silently drop any later, less-indented item.
      const base = Math.min(...items.map((it) => it.indent))
      const [list] = renderList(items, 0, base, key++)
      out.push(list)
      continue
    }

    para.push(trimmed)
    i += 1
  }
  flushPara()
  return out
}

/** Rendered, read-only Markdown preview (theme-aware via .ab-prose). */
export function Markdown({ markdown }: { markdown: string }) {
  return <div className="ab-prose md-rendered">{renderMarkdown(markdown)}</div>
}
