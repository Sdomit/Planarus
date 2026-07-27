# Planarus select-to-capture (browser extension)

Select text on any page → right-click → **Add to Planarus** → pick a type. A tab
opens on your running Planarus with the create form already filled in.

Optionally, a toolbar badge shows how many approvals are waiting for you (#108,
slice 18.2) — see [Badge](#badge-optional-108) below.

Plain files, no build step, not part of the pnpm workspace. Chrome/Edge (MV3).

## Install (load unpacked)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode**.
3. **Load unpacked** → select this `apps/extension/` folder.
4. Make sure Planarus is running, then right-click a selection on any page.

Reload the extension from that same page after editing any file here.

## Point it at your Planarus

Defaults to `http://localhost:5173`, which is right for a normal single-machine
install — nothing to configure.

For a shared install on your network, or a hosted one, right-click the toolbar
icon → **Options** and set **Planarus app URL** to that address
(`http://192.168.1.42:5173`). The app's own "copy LAN address" button, in the
account menu, gives you the exact value. Everyone on the team sets their own; no
file is edited and the browser asks for no permission, because this only decides
which tab gets opened.

Leave it blank to fall back to the localhost default in
[`capture-url.js`](capture-url.js).

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
- **Firefox/Safari.** MV3 service workers and `chrome.*` differ enough to want
  their own pass.

## Badge (optional, #108)

Shows the number of approvals waiting for you in the toolbar, without opening
Planarus. This is the *only* part of the extension that holds a credential and
makes a network call — select-to-capture above holds neither (D65). Off by
default; nothing is stored or requested until you fill in the options page.

1. In Planarus: **Settings → API Clients** → issue a key with **Read** only
   (no Propose) scoped to the project you want the count for.
2. Right-click the extension's toolbar icon → **Options** (or open it from
   `chrome://extensions`). Enter your Planarus API URL (e.g.
   `http://localhost:8000`) and the key, then **Save**.
3. Chrome will ask you to approve access to that one origin — this is
   `optional_host_permissions` being requested for exactly the URL you typed,
   not a broad grant taken at install.

The badge polls in the background (`apps/extension/background.js` +
`badge.js`) and clears itself — no count shown — the moment the key is
missing, wrong, revoked, or the API is unreachable; it never shows a stale or
guessed number. An unreachable API is polled less and less often (backoff, capped
at 30 minutes) rather than hammered. Clicking the badge opens the Approval
Queue in the app; there is deliberately **no approve/reject in a popup** — you
review the same diff preview you always would (D65's whole point: the human
seeing the preview is the product).

To turn it off, clear both fields on the options page and Save.

## Contract

`captureUrl()` in [`capture-url.js`](capture-url.js) emits:

```
<APP_URL>#capture=<uriComponent({ type, text, url?, title? })>
```

The other half is `parseCapture()` in `apps/web/src/app/capture.ts`, which
validates it on arrival — unknown type, empty text, or a non-http(s) URL is
rejected there too. If you change one, change both; the contract test in
`apps/web/src/app/extension-contract.test.ts` is what fails if you don't.
