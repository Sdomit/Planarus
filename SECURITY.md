# Security Policy

Approvo is a **trust product**: AI agents *propose*, humans *approve*. Its
security model is the point, so we take reports seriously.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through **GitHub's private vulnerability reporting**: on this
repository, go to the **Security** tab → **Report a vulnerability** (this opens a
private advisory only the maintainer can see). Include:

- what you found and where (file/endpoint if known),
- how to reproduce it,
- the impact you think it has.

You'll get an acknowledgement within a few days. Since this is a solo,
pre-1.0 project, please allow reasonable time for a fix before any public
disclosure. Coordinated disclosure is appreciated and credited.

> Maintainer note: private reporting must be enabled once under
> **Settings → Advanced Security → Private vulnerability reporting** for the link
> above to appear.

## Supported versions

Pre-1.0: only the current `main` branch is supported. There are no backported
security fixes for older commits or tags yet.

## Security model (what you're testing against)

Approvo is local-first and self-hosted. The invariants below are load-bearing
— a bug that breaks one of them is a security bug:

- **Every external-AI write is approval-gated.** External clients (MCP, the HTTP
  external API, a future GPT Action) may only *read* or *create pending
  proposals* — never approve, apply, reject, or invalidate. A single internal
  engine is the one apply path.
- **The external API is disabled by default** and binds `127.0.0.1` only. Remote
  exposure is an explicit, documented user opt-in fronted by the user's own HTTPS.
- **DNS-rebinding defense:** a Host-header allowlist is enforced on *every* HTTP
  request; `X-Forwarded-*` is never trusted.
- **Untrusted tool/endpoint output** is boundary-wrapped, secret-redacted, and
  re-scanned before it reaches an agent; paths, tokens, and DB URLs are never
  leaked.

If you can make an external client mutate state without human approval, reach a
non-loopback bind, bypass the Host guard, or exfiltrate a secret through rendered
output, that's exactly what we want to hear about.

## Out of scope

- Findings that require the user to have already enabled the external API and
  deliberately exposed it without the documented HTTPS/host-guard setup.
- Missing hardening on features explicitly documented as local-only,
  disabled-by-default, or opt-in.
