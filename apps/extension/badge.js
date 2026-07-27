/**
 * Pending-approval badge logic (#108, slice 18.2 — deliberately deferred in
 * #107's README until now, because this is the one thing 18.0/18.1 avoid
 * entirely: a stored credential and a network call).
 *
 * Kept separate from background.js for the same reason as capture-url.js: a
 * service worker cannot be imported by a test runner. `fetchImpl` is always
 * injected, so nothing in this file ever makes a real network call under test.
 */

export const EXTERNAL_BASE = '/api/external/v1'

/** Normal poll cadence. Chrome enforces a 1-minute floor on repeating alarms
 *  anyway, so this is also the practical minimum. */
export const POLL_MINUTES = 1
/** Backoff ceiling — an unreachable API is checked at most this rarely. */
export const MAX_BACKOFF_MINUTES = 30

/**
 * Delay before the next poll. Doubles per consecutive failure and caps at
 * MAX_BACKOFF_MINUTES (#108 AC5) — a Planarus that is not running gets
 * checked less and less often, not hammered every minute forever.
 */
export function nextDelayMinutes(consecutiveFailures) {
  if (!Number.isFinite(consecutiveFailures) || consecutiveFailures <= 0) return POLL_MINUTES
  return Math.min(POLL_MINUTES * 2 ** consecutiveFailures, MAX_BACKOFF_MINUTES)
}

/** Chrome clears a toolbar badge on an empty string — the whole contract for
 *  "nothing pending" (#108 AC1). Three digits is as far as a badge can read. */
export function badgeText(count) {
  if (!Number.isFinite(count) || count <= 0) return ''
  return count > 99 ? '99+' : String(count)
}

async function getJson(fetchImpl, url, apiKey) {
  const res = await fetchImpl(url, { headers: { Authorization: `Bearer ${apiKey}` } })
  if (!res.ok) throw new Error(`request to ${url} failed: ${res.status}`)
  return res.json()
}

/**
 * One poll cycle: list the key's in-scope projects (no project id needed —
 * the key already carries its own scope), then sum each project's pending
 * count. A read-only key is conventionally issued for exactly one project,
 * but this sums whatever the key can see rather than assuming that.
 *
 * Never throws (#108 AC3): a missing/unset key, an invalid/expired/revoked
 * key, or an unreachable Planarus must all degrade to `{ ok: false }` — a
 * cleared badge, not an error surfaced to the user or a crash loop.
 */
export async function fetchPendingTotal(apiUrl, apiKey, fetchImpl) {
  if (!apiUrl || !apiKey) return { ok: false, count: 0 }
  try {
    const projects = await getJson(fetchImpl, `${apiUrl}${EXTERNAL_BASE}/projects`, apiKey)
    const ids = projects?.metadata?.project_ids
    if (!Array.isArray(ids)) return { ok: false, count: 0 }

    let total = 0
    for (const id of ids) {
      if (typeof id !== 'string' || !id) continue
      const url = `${apiUrl}${EXTERNAL_BASE}/projects/${encodeURIComponent(id)}/approvals/pending-count`
      const body = await getJson(fetchImpl, url, apiKey)
      const count = body?.metadata?.pending_count
      if (typeof count === 'number' && Number.isFinite(count)) total += count
    }
    return { ok: true, count: total }
  } catch {
    return { ok: false, count: 0 }
  }
}
