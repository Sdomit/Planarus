# Handoff — public-release readiness for Planarus

20260727-191526 · repo Planarus-public · branch main

## Goal

Get the (already public) repo into a state a non-developer can install and run —
solo, on a LAN, and with AI agents — and make the Windows path actually work.

## Status

- Done: audited install / LAN / AI-agent / release hygiene. Fixed 6 dead doc links, removed CI `paths` filters, rewrote `docs/github-settings.md`, populated `CHANGELOG.md`, aligned all 4 version manifests on `0.2.0`.
- Done: Node 20 (EOL) → 24 everywhere; 14 of Dependabot's 15 JS updates taken; **jsdom held at 29** (jsdom 30's CSS engine throws from `getComputedStyle`, which testing-library calls on every visibility check).
- Done: Windows path made real — winget bootstrap in `run-planarus.bat`, plus `stop-planarus.bat`, `planarus-tray.bat`/`.ps1`, `create-shortcuts.bat`, `update-planarus.bat`.
- Done: fixed 4 fatal Windows bugs (below) and added a `windows-latest` CI job, because nothing had ever executed these scripts.
- Done: branch ruleset on `main` — `deletion` + `non_fast_forward` only.
- In progress: nothing. Tree clean, synced with `origin/main` at `691f080`, CI green.
- Blocked: none.

## Next step

Verify the quickstart on a **clean machine** (fresh Docker, empty clone, no Node/Python). CI proves the Docker stack builds and that the launcher cold-bootstraps a venv — neither is the same as a stranger installing from scratch. This is the last real unknown before promoting the repo.

## Key files

- `scripts/run-planarus.bat` — Windows launcher; winget bootstrap, venv, ports, health checks. Writes `%LOCALAPPDATA%\Planarus\local.ports`.
- `scripts/planarus-tray.ps1` — tray icon (WinForms, zero new deps). Logs to `%LOCALAPPDATA%\Planarus\tray.log`.
- `scripts/update-planarus.bat` — rebase + refresh both dep trees; guards dirty tree and force-pushed upstream.
- `.github/workflows/ci.yml` — 6 jobs; `windows-scripts` is the new one. No `paths` filters (public repo, unmetered).
- `.github/dependabot.yml` — jsdom major held, with the reason.
- `docs/github-settings.md` — what the ruleset actually enforces and why the PR rule was omitted.

## Decisions & gotchas

- **No pull requests.** Work lands by rebasing onto `main` and pushing directly. Don't run `gh pr create`.
- **`required_status_checks` must NOT be re-added** while pushing directly to `main`. It blocks direct pushes (`4 of 4 required status checks are expected`) and CI only triggers on push-to-main/PR, so the checks can never exist beforehand — an unsatisfiable lockout. It was applied once and removed within minutes.
- **Replace rulesets with `PUT`, never DELETE-then-POST** — a force-push landed in a 7-second gap between the two today. Also avoid `gh api -F 'rules[][type]=…'`; the flag form silently built the wrong ruleset. Use `--input`.
- **Three cmd batch traps** that caused today's bugs, all avoided by construction in new scripts: `%~f` inside a `REM` is still substituted (aborts the file on parse); a `%VAR%` read inside a parenthesised block is substituted at *parse* time, before the subroutine that sets it runs; an unescaped `>` in `echo` is a redirect.
- **Another session pushes to `main` concurrently** — always `git pull --rebase` before pushing.
- `main` moves under you: `1085e37`/`66bd75f` (Notion-style doc editor) came from outside this session.
- Web and API must share one hostname — the web client calls a relative `/api/v1`, there is no build-time API URL.

## Resume

- Branch: `git checkout main` (state: committed and pushed, clean)
- Verify: `pnpm --filter @planarus/web test` · `cd apps/api && .venv\Scripts\python.exe -m pytest` · `docker compose up --build`
- Open questions: adopt the `pull_request` ruleset rule (costs the no-PR workflow)? `@types/node` is `^26` against a Node 24 runtime — typecheck can green-light APIs that don't exist at runtime.

## Resume prompt (paste into new chat)

> Continue public-release work on Planarus-public, branch `main`. Read `docs/HANDOFF.md` first.
> Next: verify the quickstart on a clean machine (fresh Docker, empty clone, no Node/Python).
> Constraints: no pull requests — rebase onto `main` and push directly. Never re-add
> `required_status_checks` to the ruleset; it locks out direct pushes. Another session
> pushes to `main` concurrently, so always `git pull --rebase` first.
