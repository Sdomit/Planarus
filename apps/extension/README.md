# Planarus select-to-capture (browser extension)

Select text on any page → right-click → **Add to Planarus** → pick a type. A tab
opens on your running Planarus with the create form already filled in.

Three files, no build step, not part of the pnpm workspace. Chrome/Edge (MV3).

## Install (load unpacked)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode**.
3. **Load unpacked** → select this `apps/extension/` folder.
4. Make sure Planarus is running, then right-click a selection on any page.

Reload the extension from that same page after editing any file here.

## Point it at your Planarus

`APP_URL` at the top of [`capture-url.js`](capture-url.js) — one line:

```js
export const APP_URL = 'http://localhost:5173'
```

Change it to your LAN address (`http://192.168.1.42:5173`) or hosted origin. The
app's own "copy LAN address" button, in the account menu, gives you the exact
value.

## What it does and does not do

It holds **no credential**, requests **no host permission**, and makes **no
network call**. It builds a URL and opens a tab; everything after that is the
app, in your own logged-in session (D65). Nothing is created until you press the
button on the form that opens — the extension cannot write to Planarus, and a
captured clip is never an agent proposal.

The clip travels in the URL **fragment** (`#capture=…`), which browsers do not
send to servers, so selected text never lands in an access log.

The active project is whatever you last had open in the app (D67). The extension
does not know your projects and never asks.

## Types

**Task · Phase · Decision · Risk · Note (todo) · Note (doc)** — chosen in the
native submenu, so there is no popup to build and no picker to keep in sync
(D66). Assignee, status and phase are set in the app's own form, where the real
options live.

## Not included

- **Icons.** Chrome shows a default placeholder in the toolbar and menu. Drop
  `icons/16.png`, `icons/48.png` and `icons/128.png` here and add an `"icons"`
  block to `manifest.json` to brand it.
- **Pending-approval badge.** That is slice 18.2 (#108), deliberately deferred:
  it needs a read-only API key and a polling network call, which is exactly what
  this slice avoids.
- **Firefox/Safari.** MV3 service workers and `chrome.*` differ enough to want
  their own pass.

## Contract

`captureUrl()` in [`capture-url.js`](capture-url.js) emits:

```
<APP_URL>#capture=<uriComponent({ type, text, url?, title? })>
```

The other half is `parseCapture()` in `apps/web/src/app/capture.ts`, which
validates it on arrival — unknown type, empty text, or a non-http(s) URL is
rejected there too. If you change one, change both; the contract test in
`apps/web/src/app/extension-contract.test.ts` is what fails if you don't.
