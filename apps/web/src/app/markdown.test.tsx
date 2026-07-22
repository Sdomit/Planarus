import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { Markdown } from './markdown'

afterEach(cleanup)

describe('Markdown renderer', () => {
  it('renders headings, lists, code and inline marks', () => {
    const md = [
      '# Title',
      '',
      'Some **bold** and *italic* and `code`.',
      '',
      '- first',
      '- second',
      '  - nested',
      '',
      '```py',
      'print("hi")',
      '```',
    ].join('\n')
    const { container } = render(<Markdown markdown={md} />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Title')
    expect(container.querySelector('strong')?.textContent).toBe('bold')
    expect(container.querySelector('em')?.textContent).toBe('italic')
    expect(container.querySelectorAll('ul').length).toBe(2) // outer + nested
    expect(container.querySelector('pre.md-code code')?.textContent).toBe('print("hi")')
  })

  it('keeps items that dedent below the first item indent', () => {
    const { container } = render(<Markdown markdown={'  - a\n- b'} />)
    expect(container.textContent).toContain('a')
    expect(container.textContent).toContain('b')
  })

  it('renders GFM tables', () => {
    const md = ['| A | B |', '|---|---|', '| 1 | 2 |'].join('\n')
    const { container } = render(<Markdown markdown={md} />)
    expect(container.querySelectorAll('th').length).toBe(2)
    expect(container.querySelectorAll('td').length).toBe(2)
    expect(screen.getByText('1')).toBeTruthy()
  })

  it('renders frontmatter as a metadata block, not headings', () => {
    const md = ['---', 'kind: next_step', '---', '# Real heading'].join('\n')
    const { container } = render(<Markdown markdown={md} />)
    expect(container.querySelector('.md-frontmatter')?.textContent).toContain('kind: next_step')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Real heading')
  })

  it('keeps safe links and neutralizes javascript: URLs', () => {
    const md = '[ok](https://example.com) and [bad](javascript:alert(1))'
    const { container } = render(<Markdown markdown={md} />)
    const links = container.querySelectorAll('a')
    expect(links.length).toBe(1)
    expect(links[0].getAttribute('href')).toBe('https://example.com')
    expect(links[0].getAttribute('rel')).toContain('noopener')
    expect(container.textContent).toContain('bad') // label survives as text
  })

  it('never injects raw HTML from content', () => {
    const { container } = render(<Markdown markdown={'hello <img src=x onerror=alert(1)>'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>')
  })
})

describe('bare URL autolinking', () => {
  const hrefOf = (t: string) => {
    render(<Markdown markdown={t} />)
    return screen.queryByRole('link')?.getAttribute('href') ?? null
  }

  it('links a URL pasted straight into a note', () => {
    expect(hrefOf('see https://example.com for context')).toBe('https://example.com')
  })

  it('leaves sentence punctuation out of the href', () => {
    expect(hrefOf('read https://example.com/docs.')).toBe('https://example.com/docs')
    expect(screen.getByRole('link').textContent).toBe('https://example.com/docs')
  })

  it('does not double-handle a markdown link', () => {
    render(<Markdown markdown={'[the docs](https://example.com/a)'} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute('href')).toBe('https://example.com/a')
    expect(links[0].textContent).toBe('the docs')
  })

  it('never autolinks a dangerous scheme', () => {
    // Only http(s) is matched at all, so this stays inert text.
    render(<Markdown markdown={'javascript:alert(1)'} />)
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('opens autolinks safely in a new tab', () => {
    render(<Markdown markdown={'https://example.com'} />)
    const a = screen.getByRole('link')
    expect(a.getAttribute('rel')).toBe('noreferrer noopener')
    expect(a.getAttribute('target')).toBe('_blank')
  })
})
