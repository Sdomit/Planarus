import { describe, it, expect } from 'vitest'
import { normalizeUrl } from './EntityNotes'

describe('normalizeUrl', () => {
  it('accepts what people actually paste, without a scheme', () => {
    // The reported bug: <input type="url"> rejected this outright, so the
    // browser blocked submit with "Please enter a URL" and no way forward.
    expect(normalizeUrl('www.sarmaddomit.com')).toBe('https://www.sarmaddomit.com/')
    expect(normalizeUrl('example.com/docs')).toBe('https://example.com/docs')
  })

  it('leaves an explicit scheme alone', () => {
    expect(normalizeUrl('http://example.com/x')).toBe('http://example.com/x')
    expect(normalizeUrl('https://example.com/x')).toBe('https://example.com/x')
  })

  it('trims surrounding whitespace from a paste', () => {
    expect(normalizeUrl('  example.com  ')).toBe('https://example.com/')
  })

  it('rejects non-web schemes rather than storing an injection vector', () => {
    expect(normalizeUrl('javascript:alert(1)')).toBeNull()
    expect(normalizeUrl('data:text/html,<script>')).toBeNull()
    expect(normalizeUrl('file:///etc/passwd')).toBeNull()
  })

  it('rejects a bare word, which is a typo rather than a host', () => {
    expect(normalizeUrl('notaurl')).toBeNull()
    expect(normalizeUrl('')).toBeNull()
    expect(normalizeUrl('   ')).toBeNull()
  })
})
