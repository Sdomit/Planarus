/**
 * The `#capture=` contract, in one place (#107, slice 18.1).
 *
 * Kept separate from background.js for one reason: a service worker cannot be
 * imported by a test runner, and this is the only part of the extension with
 * logic worth pinning. The app-side parser (`apps/web/src/app/capture.ts`,
 * #106) is the other half — if these two drift, capture silently stops working.
 */

/** Where the app is served, when the options page has not been given a value.
 *  A LAN or hosted install sets its own there; nothing here needs editing. */
export const APP_URL = 'http://localhost:5173'

/** #108: the badge's click-through — must match `OPEN_APPROVALS_FRAGMENT` in
 *  `apps/web/src/app/capture.ts` exactly; `extension-contract.test.ts` guards it. */
export const OPEN_APPROVALS_FRAGMENT = '#open-approvals'

/** URL the badge opens on click. No payload, so unlike `captureUrl` this never
 *  returns null — there is nothing to validate. */
export function openApprovalsUrl(appUrl) {
  return `${appUrl}${OPEN_APPROVALS_FRAGMENT}`
}

/** Mirrors MAX_TEXT in the app's parser, which clips anything longer anyway. */
export const MAX_TEXT = 4000

/** The six the context menu offers, in menu order (D66). */
export const CAPTURE_TYPES = [
  { type: 'task', label: 'Task' },
  { type: 'phase', label: 'Phase' },
  { type: 'decision', label: 'Decision' },
  { type: 'risk', label: 'Risk' },
  { type: 'todo', label: 'Note (todo)' },
  { type: 'doc', label: 'Note (doc)' },
]

/** Only http(s) survives. A chrome:// or file:// page URL is not a source a
 *  human can follow later, and the app rejects it on arrival regardless. */
function sourceUrl(value) {
  if (typeof value !== 'string') return undefined
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? value : undefined
  } catch {
    return undefined
  }
}

/**
 * Build the URL that opens the app with a clip.
 *
 * The payload rides in the **fragment**, never the query string: a fragment is
 * not sent to the server, so the clipped text never reaches an access log
 * (D65 — this extension holds no credential and makes no request of its own).
 *
 * Returns null when there is nothing worth opening a tab for.
 */
export function captureUrl(appUrl, { type, text, url, title }) {
  const clip = typeof text === 'string' ? text.trim().slice(0, MAX_TEXT) : ''
  if (!clip) return null
  if (!CAPTURE_TYPES.some((t) => t.type === type)) return null

  const payload = { type, text: clip }
  const source = sourceUrl(url)
  if (source) payload.url = source
  if (typeof title === 'string' && title.trim()) payload.title = title.trim()

  return `${appUrl}#capture=${encodeURIComponent(JSON.stringify(payload))}`
}
