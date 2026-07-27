/**
 * Options page logic: where the app runs, and the pending-approval badge
 * (#108, slice 18.2).
 *
 * The two halves are deliberately independent. The app URL only chooses which
 * tab `chrome.tabs.create` opens, so it is saved with no permission prompt and
 * works with the badge switched off — that is what keeps a LAN or hosted
 * install from having to edit `capture-url.js` by hand. Saving the badge's API
 * URL requests `host_permissions` for exactly that origin, because MV3 requires
 * the grant before this extension's own `fetch()` calls will succeed. Nothing
 * is persisted or requested until Save is pressed.
 */
import { badgeText, fetchPendingTotal } from './badge.js'

const form = document.getElementById('form')
const appUrlInput = document.getElementById('appUrl')
const apiUrlInput = document.getElementById('apiUrl')
const apiKeyInput = document.getElementById('apiKey')
const status = document.getElementById('status')

function setStatus(message, kind) {
  status.textContent = message
  status.className = kind ?? ''
}

/** The origin as a match pattern, or null if that is not a usable URL. */
function originPattern(value) {
  try {
    const { protocol, origin } = new URL(value)
    // A successful parse is not enough. `localhost:5173` — the likeliest thing
    // to type — parses happily as protocol "localhost:" with a *null* origin,
    // so without this check it saved the literal string "null/*" and the badge
    // then asked for a permission that could never be granted.
    return protocol === 'http:' || protocol === 'https:' ? `${origin}/*` : null
  } catch {
    return null
  }
}

/** Every save path reports the app URL, since it is saved on every one. */
function appUrlSaved(appUrl) {
  return appUrl ? `App URL saved (${appUrl}).` : 'App URL: default (localhost:5173).'
}

async function load() {
  const { appUrl, apiUrl, apiKey } = await chrome.storage.local.get([
    'appUrl', 'apiUrl', 'apiKey',
  ])
  // Placeholders already show the defaults, so an unset field stays empty
  // rather than pretending a value was chosen.
  appUrlInput.value = appUrl ?? ''
  apiUrlInput.value = apiUrl ?? 'http://localhost:8000'
  apiKeyInput.value = apiKey ?? ''
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  const appUrl = appUrlInput.value.trim().replace(/\/+$/, '')
  const apiUrl = apiUrlInput.value.trim().replace(/\/+$/, '')
  const apiKey = apiKeyInput.value.trim()

  // App URL first, and on its own: it must save even when the badge is off,
  // and a bad value here should not be reported as a badge problem.
  if (appUrl && !originPattern(appUrl)) {
    setStatus('The app URL needs the http:// prefix (e.g. http://192.168.1.42:5173).', 'error')
    return
  }
  if (appUrl) {
    await chrome.storage.local.set({ appUrl })
  } else {
    await chrome.storage.local.remove('appUrl')
  }

  // Both badge fields blank: turn the badge off, cleanly, no permission to
  // request. The app URL just saved above is untouched.
  if (!apiUrl && !apiKey) {
    await chrome.storage.local.remove(['apiUrl', 'apiKey'])
    setStatus(`${appUrlSaved(appUrl)} Badge disabled.`, 'ok')
    return
  }

  const pattern = originPattern(apiUrl)
  if (!pattern) {
    setStatus('The API URL needs the http:// prefix (e.g. http://localhost:8000).', 'error')
    return
  }

  setStatus('Requesting permission for that origin…')
  const granted = await chrome.permissions.request({ origins: [pattern] })
  if (!granted) {
    setStatus('Permission was not granted — the badge cannot reach that origin.', 'error')
    return
  }

  await chrome.storage.local.set({ apiUrl, apiKey })

  setStatus('Saved. Checking…')
  const { ok, count } = await fetchPendingTotal(apiUrl, apiKey, fetch)
  if (!ok) {
    setStatus(`${appUrlSaved(appUrl)} Badge saved, but that URL/key did not respond — check both and try again.`, 'error')
    return
  }
  setStatus(
    `${appUrlSaved(appUrl)} ${count} approval(s) pending right now ` +
      `(badge: "${badgeText(count)}").`,
    'ok',
  )
})

load()
