/**
 * Planarus select-to-capture — MV3 service worker (#107, slice 18.1).
 *
 * The whole extension: register a context-menu submenu, and on click open the
 * app at `#capture=…`. It holds no credential, requests no host permission, and
 * makes no network call of its own (D65) — `chrome.tabs.create` is a navigation,
 * not a request this extension can read.
 */
import { APP_URL, CAPTURE_TYPES, captureUrl } from './capture-url.js'

const PARENT_ID = 'planarus-capture'

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
