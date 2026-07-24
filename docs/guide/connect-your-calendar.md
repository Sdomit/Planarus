# Connect your calendar (Google / Microsoft) — manual setup

A follow-along guide for syncing a **Google** or **Microsoft/Outlook** calendar
with an Planarus project. You run every step yourself; nothing here happens
automatically, and it stays completely off until you finish the setup.

> **Time:** ~15 minutes the first time (most of it is registering the app with
> Google or Microsoft).
> **Safety:** your login stays with Google/Microsoft — Planarus only receives an
> access token, which it stores **encrypted** and never shows you or anyone
> else. Disconnect at any time to delete it. Sync is **off by default**.

---

## What it does

- **Push** — events you create in Planarus's Calendar are copied to your Google/
  Microsoft calendar.
- **Pull** — events from that calendar appear in Planarus, alongside your
  milestones and due tasks.

Only standalone (non-recurring) events sync for now. Milestones and tasks are
shown in the calendar but are managed from Planning, not pushed out.

## What you need before you start

- **Planarus running locally** (`run-planarus.sh` on macOS/Linux, `run-planarus.bat` on Windows —
  opens the API on `:8000` and
  the UI on `:5173`).
- A **Google** and/or **Microsoft** account.
- The Python calendar-sync extra (installed in Step 3).

You do **not** need a domain or a tunnel — this runs entirely on `localhost`.

---

## Step 1 — Generate an encryption key

Planarus encrypts the calendar tokens it stores. Generate a key once, in
PowerShell from `apps/api`:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the line it prints — that's your `PLANARUS_CALENDAR_ENC_KEY`. Keep it
stable: if you change it later, existing connections stop working and you just
reconnect. Treat it like a password — don't commit it.

## Step 2 — Register an OAuth app

You only need the provider(s) you'll actually use.

### Google

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) → create
   (or pick) a project.
2. **APIs & Services → Library →** enable the **Google Calendar API**.
3. **APIs & Services → OAuth consent screen →** set it up (External is fine),
   and add **yourself** as a test user so you can use it before it's verified.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →**
   application type **Web application**.
5. Under **Authorized redirect URIs**, add exactly:
   ```
   http://localhost:5173/api/v1/calendar-sync/google/callback
   ```
6. Save. Copy the **Client ID** and **Client secret**.

### Microsoft

1. Go to the [Azure Portal](https://portal.azure.com/) → **Microsoft Entra ID**
   (Azure AD) → **App registrations → New registration**.
2. Give it a name. Under **Redirect URI**, choose platform **Web** and enter:
   ```
   http://localhost:5173/api/v1/calendar-sync/microsoft/callback
   ```
3. Register. Copy the **Application (client) ID**.
4. **Certificates & secrets → New client secret →** copy the secret **Value**
   (not the ID) right away.
5. **API permissions → Add a permission → Microsoft Graph → Delegated
   permissions →** add **`Calendars.ReadWrite`** and **`offline_access`**.

## Step 3 — Configure Planarus

Add the values to your environment (e.g. an `.env` file that `apps/api` reads).
Set only the provider(s) you registered:

```
PLANARUS_CALENDAR_ENC_KEY=<the key from Step 1>

PLANARUS_CALENDAR_GOOGLE_CLIENT_ID=<Google client id>
PLANARUS_CALENDAR_GOOGLE_CLIENT_SECRET=<Google client secret>

PLANARUS_CALENDAR_MICROSOFT_CLIENT_ID=<Microsoft client id>
PLANARUS_CALENDAR_MICROSOFT_CLIENT_SECRET=<Microsoft client secret>

# Required: the exact callback URL(s) you registered above, comma-separated.
PLANARUS_OAUTH_REDIRECT_URIS=http://localhost:5173/api/v1/calendar-sync/google/callback
```

Install the extra and restart the API (from `apps/api`):

```powershell
.\.venv\Scripts\pip.exe install -e ".[calendar-sync]"
```

Then relaunch (`run-planarus.sh` on macOS/Linux, `run-planarus.bat` on Windows).

> **Both are required.** With no encryption key, or no client id, sync stays
> off — the button below simply shows "not configured". A provider only appears
> once **both** its client id and the encryption key are set.

> **Third thing required (#113):** `PLANARUS_OAUTH_REDIRECT_URIS` must contain
> the callback URL, character for character, including the port. Connect refuses
> with **400 redirect_uri is not allowlisted** otherwise. The connect→callback
> round trip is also one-time and tied to the browser that started it, so finish
> it in the window it opened; in team mode the callback must land in the same
> signed-in account, which needs an editor or owner role on the project.

## Step 4 — Connect from the app

1. Open Planarus → pick a project → **Calendar** (left sidebar, under Workspace).
2. Click **Sync** in the toolbar.
3. Click **Connect Google** (or **Connect Microsoft**). A popup opens on the
   provider's own sign-in page.
4. Sign in **there** and approve calendar access. The popup closes itself.
5. The dialog now lists your account — e.g. `google · you@example.com ·
   connected`.

You entered your password on Google/Microsoft's page, never in Planarus.

## Step 5 — Sync

In the same **Sync** dialog, click **Sync now** on the connection. Planarus
pushes your new local events out and pulls the calendar's events in; it reports
e.g. "pushed 2, pulled 5". Run it whenever you want the two sides reconciled.

## Turning it off

- **Disconnect** (in the Sync dialog) deletes the stored token for that
  connection. Planarus can no longer reach that calendar.
- To revoke from the other side too, remove Planarus's access in your
  [Google Account permissions](https://myaccount.google.com/permissions) or
  Microsoft [My Apps](https://myapps.microsoft.com/).
- Removing `PLANARUS_CALENDAR_ENC_KEY` (or the client ids) from the
  environment disables sync entirely on the next restart.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sync dialog says "not configured" | The encryption key **and** a client id must both be set; restart the API after editing `.env`. |
| "redirect_uri_mismatch" in the popup | The redirect URI in Google/Azure must match **exactly** (scheme, host, port, path), including `http://localhost:5173`. |
| Popup signs in but nothing appears | You may have used a different port — register the redirect URI for the port you actually open the app on. |
| "access token expired and no refresh token is stored" | Reconnect; for Google make sure the consent prompt granted **offline access** (re-consent if needed). |

---

Under the hood the tokens are encrypted at rest and never returned by the API;
the design and the exact endpoints live in
[docs/dev/phase-15.12b-calendar-sync.md](../dev/phase-15.12b-calendar-sync.md).
