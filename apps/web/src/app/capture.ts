/**
 * Select-to-capture intake (#106, slice 18.0).
 *
 * The browser extension holds no credential and calls no API (D65). It opens
 * the app at `#capture=<json>` and the app does the rest, so this parser is the
 * whole trust boundary: everything here arrives from a URL anyone can type.
 *
 * The payload rides in the **fragment**, not the query string, so the clipped
 * text is never sent to the server and never lands in an access log.
 */

/** #108: the badge's whole click-through contract — no payload, just "open the
 *  queue". Bare string compare, not JSON, so there is nothing here to parse or
 *  reject; `apps/extension/capture-url.js` carries the other half. */
export const OPEN_APPROVALS_FRAGMENT = '#open-approvals'

export const CAPTURE_TYPES = ['task', 'phase', 'decision', 'risk', 'todo', 'doc'] as const

export type CaptureType = (typeof CAPTURE_TYPES)[number]

export interface Capture {
  type: CaptureType
  text: string
  url?: string
  title?: string
}

/** A clip is a selection, not a document. Longer than this is a paste mistake. */
export const MAX_TEXT = 4000
/** Long enough for any real URL, short enough that nothing silly gets stored. */
const MAX_URL = 2000
const MAX_TITLE = 300

/** Only http(s). A `javascript:` or `data:` URL here would be stored, rendered
 *  as a link, and clicked by a human — the one dangerous field in the payload. */
function safeUrl(value: unknown): string | undefined {
  if (typeof value !== 'string' || value.length > MAX_URL) return undefined
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? value : undefined
  } catch {
    return undefined
  }
}

function trimmedString(value: unknown, max: number): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed.slice(0, max) : undefined
}

/**
 * Parse a `#capture=…` fragment. Returns null for anything malformed rather
 * than throwing: a bad fragment must leave the app booting normally, since the
 * only thing standing between it and a white screen is this function.
 */
export function parseCapture(hash: string): Capture | null {
  const marker = hash.indexOf('capture=')
  if (marker === -1) return null

  let decoded: string
  try {
    decoded = decodeURIComponent(hash.slice(marker + 'capture='.length))
  } catch {
    return null  // a lone '%' is enough to throw here
  }

  let raw: unknown
  try {
    raw = JSON.parse(decoded)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null

  const payload = raw as Record<string, unknown>
  const type = payload.type
  if (typeof type !== 'string' || !CAPTURE_TYPES.includes(type as CaptureType)) return null

  const text = trimmedString(payload.text, MAX_TEXT)
  if (!text) return null  // a capture with nothing captured is not a capture

  return {
    type: type as CaptureType,
    text,
    url: safeUrl(payload.url),
    title: trimmedString(payload.title, MAX_TITLE),
  }
}

/** First line, clipped — what a title field should hold when the clip is a paragraph. */
export function captureTitle(capture: Capture, max = 120): string {
  const firstLine = capture.text.split('\n')[0].trim()
  return (firstLine || capture.text).slice(0, max)
}

/** The body a create form should start with: the clip, then where it came from. */
export function captureBody(capture: Capture): string {
  if (!capture.url) return capture.text
  const source = capture.title ? `${capture.title} — ${capture.url}` : capture.url
  return `${capture.text}\n\nSource: ${source}`
}
