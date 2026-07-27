/**
 * Planarus select-to-capture — MV3 service worker (#107 slice 18.1, #108 slice
 * 18.2).
 *
 * Select-to-capture (18.1): register a context-menu submenu, and on click open
 * the app at `#capture=…`. It holds no credential, requests no host
 * permission, and makes no network call of its own (D65) — `chrome.tabs.create`
 * is a navigation, not a request this extension can read.
 *
 * Pending-approval badge (18.2, optional): the one part of this extension that
 * holds a credential and calls the API (D77). Configured in the options page;
 * until an API URL + key are saved there, `fetchPendingTotal` short-circuits
 * and the badge simply never appears — no error, no crash loop (#108 AC3).
 */
import { APP_URL, CAPTURE_TYPES, captureUrl, openApprovalsUrl } from './capture-url.js'
import { badgeText, fetchPendingTotal, nextDelayMinutes } from './badge.js'

const PARENT_ID = 'planarus-capture'
const BADGE_ALARM = 'planarus-badge-poll'

// onInstalled only. A service worker restarts constantly, and re-registering a
// menu that already exists throws "duplicate id".
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: PARENT_ID,
      title: 'Add to Planarus',
      contexts: ['selection'],
    })
    for (const { type, label } of CAPTURE_TYPES) {
      chrome.contextMenus.create({
        id: `${PARENT_ID}:${type}`,
        parentId: PARENT_ID,
        title: label,
        contexts: ['selection'],
      })
    }
  })
  refreshBadge()
})

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (typeof info.menuItemId !== 'string' || !info.menuItemId.startsWith(`${PARENT_ID}:`)) return
  const url = captureUrl(APP_URL, {
    type: info.menuItemId.slice(PARENT_ID.length + 1),
    text: info.selectionText,
    url: tab?.url,
    title: tab?.title,
  })
  // null = nothing selected worth capturing. Opening an empty tab would be worse
  // than doing nothing.
  if (url) chrome.tabs.create({ url })
})

// --- 18.2: pending-approval badge ---------------------------------------

// A service worker restarts constantly, so failure streak lives in
// chrome.storage.session (survives worker restarts, clears on browser close)
// rather than a module-level variable, which would silently reset to 0 and
// undo the backoff every time the worker is respawned.
async function readFailureStreak() {
  const { badgeFailures } = await chrome.storage.session.get('badgeFailures')
  return typeof badgeFailures === 'number' ? badgeFailures : 0
}

async function refreshBadge() {
  const { apiUrl, apiKey } = await chrome.storage.local.get(['apiUrl', 'apiKey'])
  const { ok, count } = await fetchPendingTotal(apiUrl, apiKey, fetch)

  // #108 AC3: no key configured, or the API refused/was unreachable — clear
  // the badge quietly rather than show a stale or wrong number.
  await chrome.action.setBadgeText({ text: ok ? badgeText(count) : '' })
  await chrome.action.setBadgeBackgroundColor({ color: '#b00020' })

  const failures = ok ? 0 : (await readFailureStreak()) + 1
  await chrome.storage.session.set({ badgeFailures: failures })
  // #108 AC5: reschedule as a one-off alarm rather than a fixed period, so the
  // delay can grow with the failure streak and reset the moment it recovers.
  chrome.alarms.create(BADGE_ALARM, { delayInMinutes: nextDelayMinutes(failures) })
}

chrome.runtime.onStartup.addListener(refreshBadge)
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === BADGE_ALARM) refreshBadge()
})
// Saving the options page (or clearing it) should reflect immediately, not
// wait out whatever backoff the last failure streak left behind.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && (changes.apiUrl || changes.apiKey)) refreshBadge()
})

// Clicking the toolbar icon opens the queue directly (#108 AC4). No popup is
// declared in the manifest, which is what makes this event fire at all;
// approving/rejecting from a popup is an explicit non-goal (D65's "the human
// seeing the preview is the product" — see plan 18.2).
chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: openApprovalsUrl(APP_URL) })
})
