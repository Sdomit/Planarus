/**
 * Options page logic for the pending-approval badge (#108, slice 18.2).
 *
 * Saving requests `host_permissions` for exactly the entered API origin — MV3
 * requires that grant before this extension's own `fetch()` calls to it will
 * succeed. Nothing is persisted or requested until Save is pressed.
 */
import { badgeText, fetchPendingTotal } from './badge.js'

const form = document.getElementById('form')
const apiUrlInput = document.getElementById('apiUrl')
const apiKeyInput = document.getElementById('apiKey')
const status = document.getElementById('status')

function setStatus(message, kind) {
  status.textContent = message
  status.className = kind ?? ''
}

function originPattern(apiUrl) {
  try {
    return `${new URL(apiUrl).origin}/*`
  } catch {
    return null
  }
}

async function load() {
  const { apiUrl, apiKey } = await chrome.storage.local.get(['apiUrl', 'apiKey'])
  apiUrlInput.value = apiUrl ?? 'http://localhost:8000'
  apiKeyInput.value = apiKey ?? ''
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  const apiUrl = apiUrlInput.value.trim().replace(/\/+$/, '')
  const apiKey = apiKeyInput.value.trim()

  // Both blank: turn the badge off, cleanly, no permission to request.
  if (!apiUrl && !apiKey) {
    await chrome.storage.local.remove(['apiUrl', 'apiKey'])
    setStatus('Badge disabled.', 'ok')
    return
  }

  const pattern = originPattern(apiUrl)
  if (!pattern) {
    setStatus('That does not look like a URL (e.g. http://localhost:8000).', 'error')
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
    setStatus('Saved, but that URL/key did not respond — check both and try again.', 'error')
    return
  }
  setStatus(`Saved. ${count} approval(s) pending right now (badge: "${badgeText(count)}").`, 'ok')
})

load()
