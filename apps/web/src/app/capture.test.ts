import { describe, it, expect } from 'vitest'
import { parseCapture, captureBody, captureTitle, MAX_TEXT } from './capture'

const frag = (payload: unknown) => `#capture=${encodeURIComponent(JSON.stringify(payload))}`

describe('parseCapture (#106)', () => {
  it('reads a well-formed clip', () => {
    const got = parseCapture(frag({
      type: 'task', text: 'Ship the beta', url: 'https://example.com/a', title: 'Example',
    }))
    expect(got).toEqual({
      type: 'task', text: 'Ship the beta', url: 'https://example.com/a', title: 'Example',
    })
  })

  it('accepts every type the context menu offers', () => {
    for (const type of ['task', 'phase', 'decision', 'risk', 'todo', 'doc']) {
      expect(parseCapture(frag({ type, text: 'x' }))?.type).toBe(type)
    }
  })

  it('returns null rather than throwing on anything malformed', () => {
    // Each of these reaches the app as a URL a human can type or an extension
    // can get wrong; none may take the app down on boot.
    expect(parseCapture('')).toBeNull()
    expect(parseCapture('#')).toBeNull()
    expect(parseCapture('#capture=')).toBeNull()
    expect(parseCapture('#capture=%')).toBeNull()          // decodeURIComponent throws
    expect(parseCapture('#capture=notjson')).toBeNull()
    expect(parseCapture(frag([1, 2, 3]))).toBeNull()       // array, not object
    expect(parseCapture(frag(null))).toBeNull()
    expect(parseCapture(frag({ text: 'no type' }))).toBeNull()
    expect(parseCapture(frag({ type: 'invoice', text: 'x' }))).toBeNull()
    expect(parseCapture(frag({ type: 'task' }))).toBeNull()         // nothing captured
    expect(parseCapture(frag({ type: 'task', text: '   ' }))).toBeNull()
    expect(parseCapture(frag({ type: 'task', text: 42 }))).toBeNull()
  })

  it('drops a url that is not http(s) instead of storing it', () => {
    // This value ends up rendered as a link a human clicks.
    for (const url of ['javascript:alert(1)', 'data:text/html,<script>', 'file:///etc/passwd', 'nonsense']) {
      const got = parseCapture(frag({ type: 'task', text: 'x', url }))
      expect(got?.text).toBe('x')     // the clip survives…
      expect(got?.url).toBeUndefined() // …the dangerous field does not
    }
  })

  it('caps an oversized clip rather than rejecting it', () => {
    const got = parseCapture(frag({ type: 'doc', text: 'a'.repeat(MAX_TEXT + 500) }))
    expect(got?.text.length).toBe(MAX_TEXT)
  })

  it('finds the payload whether or not the fragment carries a leading #', () => {
    expect(parseCapture('capture=' + encodeURIComponent('{"type":"task","text":"x"}'))?.text).toBe('x')
  })
})

describe('capture prefill helpers', () => {
  const clip = { type: 'task' as const, text: 'Line one\nLine two', url: 'https://example.com/a', title: 'Example' }

  it('titles from the first line, not the whole paragraph', () => {
    expect(captureTitle(clip)).toBe('Line one')
  })

  it('keeps the source next to the clip in the body', () => {
    expect(captureBody(clip)).toBe('Line one\nLine two\n\nSource: Example — https://example.com/a')
  })

  it('omits the source line when the clip carries no url', () => {
    expect(captureBody({ type: 'task', text: 'bare' })).toBe('bare')
  })
})
