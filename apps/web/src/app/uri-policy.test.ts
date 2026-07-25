import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  isAllowedImageSrc,
  isAllowedLink,
  markdownTitle,
  markdownUrl,
  normalizeUrl,
} from './uri-policy'

// Built with String.fromCharCode rather than written literally: most of these are
// invisible, and a literal one in this file would be unreviewable in exactly the
// way the policy exists to prevent.
const ZERO_WIDTH_SPACE = String.fromCharCode(0x200b)
const BIDI_OVERRIDE = String.fromCharCode(0x202e)

describe('isAllowedLink', () => {
  it.each([
    'https://example.com/a/b?c=d#e',
    'http://localhost:5173/docs',
    'mailto:someone@example.com',
    'https://example.com/path_(with_parens)',
  ])('allows %s', (url) => {
    expect(isAllowedLink(url)).toBe(true)
  })

  it.each([
    'javascript:alert(1)',
    'JavaScript:alert(1)',
    'vbscript:msgbox(1)',
    'data:text/html;base64,PHNjcmlwdD4=',
    'file:///etc/passwd',
    'planarus://open/project',
    'about:blank',
  ])('refuses the %s scheme', (url) => {
    expect(isAllowedLink(url)).toBe(false)
  })

  it.each([
    'java\tscript:alert(1)', // browsers strip the tab before parsing the scheme
    'java\nscript:alert(1)',
    `https://exa${ZERO_WIDTH_SPACE}mple.com`,
    `https://example.com/${BIDI_OVERRIDE}evil`,
    'https://example.com\\@evil.test',
    'https://exa mple.com',
  ])('refuses %j for its characters', (url) => {
    expect(isAllowedLink(url)).toBe(false)
  })

  it('refuses credentials in the authority', () => {
    // Reads as trusted.example to a human, resolves to evil.test.
    expect(isAllowedLink('https://trusted.example@evil.test/')).toBe(false)
  })

  it('accepts relative references only in rich content', () => {
    expect(isAllowedLink('/docs/x')).toBe(false)
    expect(isAllowedLink('/docs/x', { allowRelative: true })).toBe(true)
    expect(isAllowedLink('#section', { allowRelative: true })).toBe(true)
    // `//evil.test` inherits the page's scheme: a remote URL in relative clothes.
    expect(isAllowedLink('//evil.test/x', { allowRelative: true })).toBe(false)
  })
})

describe('isAllowedImageSrc', () => {
  it('allows the data URIs the paste path produces', () => {
    expect(isAllowedImageSrc('data:image/jpeg;base64,/9j/4AAQSkZJRg==')).toBe(true)
    expect(isAllowedImageSrc('data:image/png;base64,iVBORw0KGgo=')).toBe(true)
  })

  it.each([
    'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=', // a document, not a raster
    'data:image/svg+xml,<svg onload=alert(1)>',
    'data:text/html;base64,PHNjcmlwdD4=',
    'data:image/png,notbase64',
    'javascript:alert(1)',
    'mailto:a@example.com',
  ])('refuses %s', (src) => {
    expect(isAllowedImageSrc(src)).toBe(false)
  })

  it('allows remote sources on purpose', () => {
    // Documented tradeoff: opening a document that carries one makes the
    // reader's browser call a third party. The toolbar depends on it.
    expect(isAllowedImageSrc('https://cdn.example.com/a.png')).toBe(true)
  })
})

describe('normalizeUrl', () => {
  it('assumes https for a bare host', () => {
    expect(normalizeUrl('example.com/docs')).toBe('https://example.com/docs')
  })

  it('keeps a bare localhost, which this tool runs on by default', () => {
    expect(normalizeUrl('localhost:8000/x')).toBeNull() // "localhost:8000" parses as a scheme
    expect(normalizeUrl('http://localhost:8000/x')).toBe('http://localhost:8000/x')
  })

  it('refuses what the shared policy refuses', () => {
    expect(normalizeUrl('javascript:alert(1)')).toBeNull()
    expect(normalizeUrl('file:///etc/passwd')).toBeNull()
    expect(normalizeUrl('notaurl')).toBeNull()
  })
})

describe('markdown escaping', () => {
  // The acceptance criterion: exported Markdown cannot be structurally broken by
  // a crafted href/src/title. A raw ")" closes `[label](href)` early and the rest
  // of the URL lands in the document as prose.
  it('wraps a URL containing a space or paren in angle brackets', () => {
    expect(markdownUrl('https://x.test/a b')).toBe('<https://x.test/a b>')
    expect(markdownUrl('https://x.test/a)![y](javascript:alert(1)')).toMatch(/^<.*>$/)
  })

  it('leaves an ordinary URL alone', () => {
    expect(markdownUrl('https://x.test/a/b?c=d')).toBe('https://x.test/a/b?c=d')
  })

  it('percent-encodes the angle brackets it would otherwise be confused by', () => {
    expect(markdownUrl('https://x.test/a>b')).toBe('https://x.test/a%3Eb')
  })

  it('escapes quotes and flattens newlines in a title', () => {
    expect(markdownTitle('say "hi"')).toBe('say \\"hi\\"')
    expect(markdownTitle('a\nb')).toBe('a b')
  })
})

//: Vitest runs with `apps/web` as its root, which is where both files live.
const WEB_ROOT = process.cwd()

describe('the deployed Content-Security-Policy', () => {
  // The CSP allows exactly one inline script: the theme resolver in index.html.
  // Edit that script without updating the hash and the page silently loses its
  // pre-paint theme, which is the kind of breakage nobody attributes to a header.
  it('carries the current hash of the inline theme script', () => {
    const html = readFileSync(resolve(WEB_ROOT, 'index.html'), 'utf-8')
    const nginx = readFileSync(resolve(WEB_ROOT, 'nginx.conf'), 'utf-8')
    const body = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1]
    expect(body).toBeTruthy()
    const hash = `sha256-${createHash('sha256').update(body as string, 'utf-8').digest('base64')}`
    expect(nginx).toContain(`'${hash}'`)
  })

  it('matches the image policy: same-origin, data URIs, and https', () => {
    const nginx = readFileSync(resolve(WEB_ROOT, 'nginx.conf'), 'utf-8')
    expect(nginx).toContain("img-src 'self' data: https:")
    expect(nginx).toContain("object-src 'none'")
    expect(nginx).toContain("frame-ancestors 'none'")
    expect(nginx).toContain("base-uri 'self'")
  })
})
