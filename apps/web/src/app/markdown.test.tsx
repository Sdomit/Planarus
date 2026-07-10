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
