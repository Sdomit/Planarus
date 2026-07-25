/** One URI policy for the browser, mirroring `apps/api/app/core/uri_policy.py` (#118).
 *
 *  The server is the enforcement point — this file cannot be, because import and
 *  direct API calls never load it. What it buys is a refusal the *author* sees
 *  while typing rather than a 422 after saving, and an inert render for rows
 *  written before the policy existed.
 *
 *  Both halves must agree. If you widen one, widen the other and the CSP in
 *  `apps/web/nginx.conf` in the same change.
 */

const LINK_SCHEMES = new Set(['http:', 'https:', 'mailto:'])

/** Raster types only. An SVG is a document, not an image, so an inline one is a
 *  markup surface we would then have to sanitize. */
const DATA_IMAGE = /^data:image\/(png|jpeg|jpg|gif|webp|avif);base64,[A-Za-z0-9+/=]+$/

/** Characters a browser strips or reinterprets *before* it decides what scheme a
 *  URL has - which is how `java<TAB>script:` gets past a naive prefix check -
 *  plus the invisible ones that make two different strings render identically.
 *  Built from escapes rather than written literally: a literal one in this
 *  pattern would be exactly the bug the pattern exists to stop. */
const FORBIDDEN = new RegExp(
  '[' +
    '\u0000-\u0020' + // C0 controls and space
    '\u007f-\u009f' + // DEL and C1 controls
    '\\\\' + //         backslash: browsers read it as "/", URL parsers differ
    '\u200b-\u200f' + // zero-width space/joiner, LTR/RTL marks
    '\u2028\u2029' + //  line and paragraph separators
    '\u202a-\u202e' + // bidi embedding and override
    '\u2066-\u2069' + // bidi isolates
    '\ufeff' + //          BOM / zero-width no-break space
    ']',
)

const MAX_LINK_LENGTH = 2000

const hasScheme = (v: string) => /^[a-z][a-z0-9+.-]*:/i.test(v)

/** True when `raw` may be stored and rendered as a hyperlink.
 *
 *  `allowRelative` is on for rich-document content, where `#section` or `/docs/x`
 *  resolves against our own origin. It is off for `Link` rows, which are
 *  bookmarks to somewhere else. */
export function isAllowedLink(raw: string, { allowRelative = false } = {}): boolean {
  const v = raw.trim()
  if (!v || v.length > MAX_LINK_LENGTH || FORBIDDEN.test(v)) return false
  if (!hasScheme(v)) {
    if (!allowRelative) return false
    // `//evil.test` inherits the page's scheme: a remote URL in relative clothes.
    if (v.startsWith('//')) return false
    return /^([/#?]|\.{1,2}\/)/.test(v)
  }
  try {
    const u = new URL(v)
    if (!LINK_SCHEMES.has(u.protocol)) return false
    if (u.protocol === 'mailto:') return v.slice('mailto:'.length).includes('@')
    // `https://trusted.example@evil.test/` reads as trusted.example to a human.
    if (u.username || u.password) return false
    if (!u.hostname) return false
    return !(u.hostname.startsWith('.') || u.hostname.endsWith('.') || u.hostname.includes('..'))
  } catch {
    return false
  }
}

/** True when `raw` may be stored and rendered as an image source.
 *
 *  Remote http(s) sources are allowed **on purpose**: the toolbar's "insert
 *  image by URL" depends on it. The cost is explicit — opening a document that
 *  carries one makes the reader's browser call a third party. */
export function isAllowedImageSrc(raw: string, { allowRelative = true } = {}): boolean {
  const v = raw.trim()
  if (!v || FORBIDDEN.test(v)) return false
  if (!hasScheme(v)) {
    if (!allowRelative || v.startsWith('//')) return false
    return /^([/]|\.{1,2}\/)/.test(v)
  }
  if (/^data:/i.test(v)) return DATA_IMAGE.test(v)
  if (v.length > MAX_LINK_LENGTH) return false
  return isAllowedLink(v) && !/^mailto:/i.test(v)
}

/** Accept what people actually paste. `www.example.com` has no scheme, so
 *  `<input type="url">` rejects it outright — the browser blocks submit before
 *  any of our code runs, and the user just sees "Please enter a URL" with no way
 *  forward. Assume https when the scheme is missing, then apply the shared
 *  policy. Returns null if it can't be salvaged. */
export function normalizeUrl(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(trimmed) ? trimmed : `https://${trimmed}`
  if (!isAllowedLink(withScheme)) return null
  if (/^mailto:/i.test(withScheme)) return withScheme
  try {
    const u = new URL(withScheme)
    // "foo" is a typo, not a host — but a bare `localhost:8000` is not, and this
    // tool runs on one by default.
    if (!u.hostname.includes('.') && u.hostname !== 'localhost') return null
    return u.href
  } catch {
    return null
  }
}

/** Markdown-safe form of a URL for `[label](href)` / `![alt](src)`.
 *
 *  A raw href is written straight into the serialized `markdown_cache`, so one
 *  containing a space or an unbalanced `)` closes the link early and the rest of
 *  the URL lands in the document as prose — which is how a crafted attribute
 *  breaks an export's structure. Markdown's angle-bracket form escapes exactly
 *  that, and percent-encoding covers the two characters it cannot hold. */
export function markdownUrl(raw: string): string {
  const encoded = raw.replace(/</g, '%3C').replace(/>/g, '%3E')
  return /[\s()]/.test(encoded) ? `<${encoded}>` : encoded
}

/** Markdown-safe form of a link/image title (the `"…"` after the URL). */
export function markdownTitle(raw: string): string {
  return raw.replace(/[\\"]/g, (c) => `\\${c}`).replace(/[\r\n]+/g, ' ')
}
