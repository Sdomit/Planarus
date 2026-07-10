# Connect AgentBoard to a private ChatGPT (read-only) — manual setup

A plain, follow-along guide for letting **your own private ChatGPT** read your
AgentBoard projects — safely, read-only, and reversible in one click. You run
every step yourself; nothing here happens automatically.

> **Time:** ~1 hour the first time (almost all of it is the Cloudflare setup).
> **Safety:** the GPT can only *read* one project. It can never approve, apply,
> change, or delete anything. You have three independent off-switches.

---

## What you need before you start

- **AgentBoard running locally** on this PC (`run-agentboard.bat` opens the API on
  `:8000` and the UI on `:5173`).
- **A domain name you own**, added to a **free Cloudflare account**
  (e.g. `example.com` — you'll use a subdomain like `agentboard.example.com`).
- **A ChatGPT plan that can create GPTs** (Plus, Team, or Enterprise).

## The picture

```
   ChatGPT  ──►  https://agentboard.example.com   ──►   your PC
              (Cloudflare, valid HTTPS)      (secure tunnel)   AgentBoard API
                                                              127.0.0.1:8000
                                                              (read-only)
```

Your PC never opens a port to the internet. Cloudflare's tunnel dials *out* from
your machine, so there's nothing inbound to expose or firewall.

---

## Step 1 — Put AgentBoard behind a public HTTPS address (Cloudflare Tunnel)

**1a. Install cloudflared.** In PowerShell:

```powershell
winget install --id Cloudflare.cloudflared
```

**1b. Log in and pick your domain** (opens a browser):

```powershell
cloudflared tunnel login
```

**1c. Create a named tunnel:**

```powershell
cloudflared tunnel create agentboard
```

Note the **Tunnel ID** it prints and the credentials file path
(`C:\Users\<you>\.cloudflared\<TunnelID>.json`).

**1d. Point your subdomain at the tunnel:**

```powershell
cloudflared tunnel route dns agentboard agentboard.example.com
```

**1e. Create the config file** `C:\Users\<you>\.cloudflared\config.yml`. The
easiest way: copy the ready-made template
[`docs/guide/cloudflared-config.template.yml`](cloudflared-config.template.yml)
there and replace the three `<PLACEHOLDERS>`. It looks like this (already scoped to
just the external API — see the hardening note below):

```yaml
tunnel: agentboard
credentials-file: C:\Users\<you>\.cloudflared\<TunnelID>.json
ingress:
  - hostname: agentboard.example.com
    path: ^/api/external/.*
    service: http://127.0.0.1:8000
    originRequest:
      httpHostHeader: agentboard.example.com
  - hostname: agentboard.example.com
    path: ^/health$
    service: http://127.0.0.1:8000
    originRequest:
      httpHostHeader: agentboard.example.com
  - service: http_status:404
```

**1f. Run the tunnel** (leave this window open while you want the GPT to work):

```powershell
cloudflared tunnel run agentboard
```

✅ **You should see:** "Registered tunnel connection" lines. Visiting
`https://agentboard.example.com/health` in a browser now returns a small JSON
health response served by AgentBoard.

> **Why the `path:` rules?** They make the tunnel forward *only* the read-only API
> (`/api/external/...`) and the health check — everything else (the local
> key-management routes, the UI) gets a 404 at the tunnel and never reaches your
> app. Those routes are already protected by a local-only credential, so this is
> belt-and-suspenders — but it's a good habit, so the template ships this way.

---

## Step 2 — Tell AgentBoard its public name (but keep the door LOCKED)

AgentBoard only accepts a public hostname you explicitly allow. Set it as a
**Windows user environment variable** so the launcher picks it up automatically.
In PowerShell:

```powershell
[Environment]::SetEnvironmentVariable("AGENTBOARD_EXTERNAL_API_ALLOWED_HOSTS","agentboard.example.com","User")
```

> Prefer clicking? Windows **Settings → System → About → Advanced system settings
> → Environment Variables → New (User)** does the same thing.

**Do not enable the API yet.** Leave `AGENTBOARD_EXTERNAL_API_ENABLED` unset for
now — the external door stays locked while you prepare the key.

Then **close every AgentBoard window and its terminal, open a fresh terminal, and
run `run-agentboard.bat` again** so the new setting takes effect (the app reads
these values once at startup).

---

## Step 3 — Create a read-only key (in the AgentBoard UI)

1. In AgentBoard (`http://localhost:5173`), open the **Clients** panel
   (left sidebar → *Agents → Clients*).
2. Click **+ New key** and fill in:
   - **Label:** `chatgpt-private-gpt-readonly`
   - **Project:** tick **one** project only.
   - **Permissions:** tick **`can_read`** only. **Leave `can_propose` unchecked.**
   - **Expires in:** `14 days`.
3. Click **Create**.
4. **Copy the key now** (it starts with `agbk_`) using the Copy button, then click
   **Done**. ⚠️ **This is the only time the key is ever shown.** Paste it somewhere
   safe for a minute — you'll hand it to the GPT in Step 5.

✅ The new key appears in the list showing **read · 1p** (read, one project).

---

## Step 4 — Turn the external API on

Now flip the door open. The easy way — run the helper script from PowerShell:

```powershell
docs\guide\set-external-api.ps1 on
```

It sets the switch, warns you if you forgot the allowlisted host, and reminds you
to restart. (Manual equivalent, if you prefer:
`[Environment]::SetEnvironmentVariable("AGENTBOARD_EXTERNAL_API_ENABLED","true","User")`.)

Then **restart AgentBoard** (close its windows, open a fresh terminal, run
`run-agentboard.bat`).

✅ **Verify from the public address** (replace the key):

```powershell
curl https://agentboard.example.com/api/external/v1/projects -H "Authorization: Bearer agbk_your_key_here"
```

You should get a **200** with your project data. Without the header, or with a
wrong key, you get an error — that's correct.

---

## Step 5 — Build your private GPT

1. In ChatGPT: **Explore GPTs → Create → Configure**.
2. Set it to **“Only me.”** *(Never publish or share a GPT that holds a key.)*
3. Scroll to **Actions → Create new action**.
4. **Import the read-only contract:** open
   [`docs/api/agentboard-gpt-actions-readonly.openapi.json`](../api/agentboard-gpt-actions-readonly.openapi.json)
   and paste its contents into the schema box.
   **Do not use** the `...read-propose...` file.
5. In the schema, set the **server URL** to `https://agentboard.example.com`
   (it ships with a placeholder).
6. **Authentication → API Key**, **Auth Type: Bearer**, and paste your `agbk_` key.
7. Save, then in the GPT preview ask something like *“List my AgentBoard
   projects”* and confirm it returns your data.

🎉 Done. Your private GPT can now read that one project, read-only.

---

## Your three panic buttons (any one closes access)

| To stop… | Do this | Effect |
| --- | --- | --- |
| **just this key** | Clients panel → **Revoke** next to the key | Key dies on the next request (one-way, permanent) |
| **all external access** | run `set-external-api.ps1 off`, restart | Every external route goes dark (404) again |
| **the whole network path** | close the `cloudflared` window | Nothing is reachable from the internet |

Practice all three once before you rely on this.

## Rotating the key (when it nears its 14-day expiry)

Create a **new** key → confirm the GPT works with it → **revoke the old** one.
Never try to edit a live key; a revoked key can never be re-enabled.

## Do / Don't

- ✅ Keep it **read-only** and **“Only me.”**
- ✅ Keep AgentBoard bound to `127.0.0.1` — the tunnel is the only public listener.
- ❌ Don't grant `can_propose` on your first key.
- ❌ Don't import the read-propose contract, and don't share/publish the GPT.
- ❌ Don't ever bind the app to `0.0.0.0`.
- 🔁 Want to share it with other people later? **Stop** and switch to a proper
  OAuth login instead of a static key — a shared static key is not safe.

## If something doesn't work

- **Every request returns 404** → the API isn't enabled, or you didn't restart
  after setting `AGENTBOARD_EXTERNAL_API_ENABLED=true` in a fresh terminal.
- **"host not allowed" / 403** → `AGENTBOARD_EXTERNAL_API_ALLOWED_HOSTS` must be the
  exact hostname (`agentboard.example.com`, no `https://`, no trailing slash), and
  you must have restarted afterward. Also confirm the `httpHostHeader:` line in your
  `config.yml` is that same hostname — it sets the `Host` the app actually checks.
- **The GPT can't reach it** → the `cloudflared` window isn't running, the server
  URL in the action isn't `https://agentboard.example.com`, or the Bearer key is
  wrong/revoked/expired.

---

*This is the friendly companion to the developer runbook at
[`docs/dev/phase-7c2b-go-live-runbook.md`](../dev/phase-7c2b-go-live-runbook.md),
which lists the exact code-verified facts behind each step.*
