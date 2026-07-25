# GitHub settings runbook

This runbook covers controls that cannot be committed in a pull request. It
does not authorize a visibility change, release, or licensing change.

## Current constraint — re-confirmed 25 July 2026

Planarus is private. GitHub's branch-protection and ruleset REST endpoints
both return: **"Upgrade to GitHub Pro or make this repository public to
enable this feature."** No repository-protection setting has been changed.

```
$ gh api repos/Sdomit/Planarus/branches/main/protection   # 403
$ gh api repos/Sdomit/Planarus/rulesets                   # 403
```

**`main` therefore has no required status checks, and the practical effect is
worse than "unprotected".** `gh pr merge --auto` does not wait for CI when there
is no required check to wait *for* — it merges on the spot. That is how #135
merged while all four jobs were still queued. Until one of the paths below is
taken, the discipline in
[../context/AGENT_RULES.md](../context/AGENT_RULES.md) — poll `gh pr checks`,
merge only on four greens — is the only gate that exists.

The owner must choose one of these paths before enforcing the controls below:

1. Keep Planarus private and upgrade the account to GitHub Pro (or move it to
   an eligible Team/Enterprise plan).
2. Make the repository public only after completing the OSS-launch privacy and
   release review. Rulesets are free on public repositories, so this path costs
   nothing — but it is gated behind #119.
3. Keep the repository private without hosted branch protection for now, while
   using the documented branch-and-PR workflow locally.

## Ready to apply — the four required checks

The moment path 1 or 2 lands, this is the whole change. The contexts are the
job names exactly as GitHub reports them; a typo creates a required check that
never arrives, which blocks every pull request until the ruleset is edited.

```bash
gh api --method POST repos/Sdomit/Planarus/rulesets --input - <<'JSON'
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true } },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "API (pytest)" },
          { "context": "API migrations (Postgres dialect)" },
          { "context": "Docker (compose build + smoke)" },
          { "context": "Web (vitest + typecheck + build)" } ] } }
  ]
}
JSON
```

Four decisions are baked into that payload, each deliberate:

- **`required_approving_review_count: 0`.** A PR author cannot approve their own
  PR, so any higher number would block every merge on a single-maintainer repo.
  Raise it when a second reviewer exists — that is the same call as §"Main
  branch" item 3, not a new one.
- **`strict_required_status_checks_policy: false`.** `true` additionally demands
  every PR be up to date with `main` before merging. This repository runs
  several concurrent sessions; strict mode would make each merge invalidate the
  others and force a rebase round-trip on all of them. The trade is real —
  strict mode catches semantic conflicts between PRs that pass independently —
  and the mitigation is that CI also runs on `main` after each merge. Revisit if
  a semantic conflict ever actually lands.
- **`bypass_actors: []`.** Nobody bypasses, the owner included. The failure this
  fixes was the owner's own tooling merging early, so an owner exemption would
  exempt precisely the actor that caused it. **Break-glass:** flip the ruleset to
  `"enforcement": "evaluate"` (reports, never blocks), do the emergency merge,
  flip it back — one `PATCH` each way, and both are visible in the audit log.
- **`non_fast_forward`.** Blocks force-pushes to `main`.

**Ordering, if this is applied to the new public repository from #119:** create
the repository, push the rewritten mirror, *then* POST the ruleset. Applied
first, `non_fast_forward` and the pull-request rule would reject the very push
that seeds the repository.

## Main branch after the plan constraint is resolved

Configure `main` as follows:

1. Require pull requests, the full CI suite, up-to-date branches, and resolved
   conversations.
2. Block force pushes and branch deletion; require linear history only after
   confirming squash merging is the normal strategy.
3. Keep required approving reviews at **zero** until a second trusted reviewer
   is available. A pull-request author cannot approve their own PR.
4. Add required CODEOWNER review only after adding that independent owner.
   `@Sdomit` is listed in CODEOWNERS to surface ownership, not to simulate an
   independent review.
5. Decide explicitly whether administrator bypass is permitted; if it is
   disabled, document a break-glass procedure first.
6. Prefer signed tags before making signed commits an enforced requirement;
   first verify every maintainer and automation path.

## Tag, release, and supply-chain controls

1. Create a tag ruleset for `v*` that blocks tag updates and deletion.
2. Enable immutable releases for future releases and create them as drafts,
   attaching checksums, SBOM, provenance/attestations, and release notes before
   publication.
3. Enable private vulnerability reporting, secret scanning/push protection when
   available, Dependabot alerts, and the existing Dependabot update workflow.
4. Use a protected release environment and environment secrets for any future
   signing credential. Never add certificate material or private keys to Git.

## Pre-release settings checklist

- Select the target version and synchronize the root, web, and API manifests.
- Confirm `LICENSE`, `NOTICE`, third-party font notices, docs, and product name
  are accurate for the release.
- Verify clean-machine install, upgrade, uninstall, backup/restore, and the
  local-only default network behavior.
- Ensure the website, release notes, repository metadata, and support/security
  routes describe the same product state.
