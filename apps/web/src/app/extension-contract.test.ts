import { describe, it, expect } from 'vitest'
import {
  captureUrl,
  CAPTURE_TYPES,
  MAX_TEXT,
  OPEN_APPROVALS_FRAGMENT as EXT_OPEN_APPROVALS_FRAGMENT,
  openApprovalsUrl,
} from '../../../extension/capture-url.js'
import { OPEN_APPROVALS_FRAGMENT as APP_OPEN_APPROVALS_FRAGMENT } from './capture'

/**
 * The extension (#107) and the app's parser (#106) are two halves of one
 * contract, and nothing else connects them — the extension is not in the pnpm
 * workspace and ships no build step. This file is what fails when they drift.
 *
 * It asserts the *emitted* shape. Once #189 lands, `parseCapture` can be
 * imported here for a true round trip; it does not exist on this branch.
 */

const APP = 'http://localhost:5173'

function payloadOf(url: string): Record<string, unknown> {
  const encoded = url.slice(url.indexOf('#capture=') + '#capture='.length)
  return JSON.parse(decodeURIComponent(encoded))
}

describe('extension → app capture contract (#107)', () => {
  it('emits the four contract fields and nothing else', () => {
    const url = captureUrl(APP, {
      type: 'task', text: 'Ship the beta', url: 'https://example.com/a', title: 'Example',
    })
    expect(url!.startsWith(`${APP}#capture=`)).toBe(true)
    expect(payloadOf(url!)).toEqual({
      type: 'task', text: 'Ship the beta', url: 'https://example.com/a', title: 'Example',
    })
  })

  it('offers exactly the six types the app accepts, in menu order', () => {
    expect(CAPTURE_TYPES.map((t: { type: string }) => t.type))
      .toEqual(['task', 'phase', 'decision', 'risk', 'todo', 'doc'])
  })

  it('refuses to open a tab for a clip with no text', () => {
    expect(captureUrl(APP, { type: 'task', text: '' })).toBeNull()
    expect(captureUrl(APP, { type: 'task', text: '   ' })).toBeNull()
    expect(captureUrl(APP, { type: 'task', text: undefined })).toBeNull()
  })

  it('refuses a type the app would reject on arrival', () => {
    expect(captureUrl(APP, { type: 'invoice', text: 'x' })).toBeNull()
  })

  it('drops a page URL that is not http(s)', () => {
    // chrome:// and file:// pages are real tabs a user can right-click on.
    for (const url of ['chrome://extensions', 'file:///c:/notes.txt', 'javascript:alert(1)']) {
      expect(payloadOf(captureUrl(APP, { type: 'task', text: 'x', url })!).url).toBeUndefined()
    }
  })

  it('caps the clip at the same length the app clips to', () => {
    const url = captureUrl(APP, { type: 'doc', text: 'a'.repeat(MAX_TEXT + 500) })
    expect((payloadOf(url!).text as string).length).toBe(MAX_TEXT)
  })

  it('encodes a clip that would otherwise break the URL', () => {
    const nasty = 'a&b=c#d %  "quoted"'
    const url = captureUrl(APP, { type: 'task', text: nasty })
    expect(url!.indexOf('#')).toBe(url!.lastIndexOf('#'))  // one fragment marker only
    expect(payloadOf(url!).text).toBe(nasty)
  })
})

describe('extension → app badge click-through contract (#108)', () => {
  it('the extension and the app agree on the exact same fragment literal', () => {
    // Unlike #capture=, this is a true round-trip check: both halves are plain
    // modules in this same test run, so there is no reason to only assert shape.
    expect(EXT_OPEN_APPROVALS_FRAGMENT).toBe(APP_OPEN_APPROVALS_FRAGMENT)
  })

  it('openApprovalsUrl appends the fragment with no payload to encode', () => {
    expect(openApprovalsUrl(APP)).toBe(`${APP}${EXT_OPEN_APPROVALS_FRAGMENT}`)
  })
})
