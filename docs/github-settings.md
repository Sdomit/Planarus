# GitHub settings runbook

This runbook covers controls that cannot be committed in a pull request. It
does not authorize a visibility change, release, or licensing change.

## Current state — public, rulesets available, not yet applied

`Sdomit/Planarus` is **public**. Rulesets are free on public repositories, so
the constraint this section used to describe — both the branch-protection and
ruleset REST endpoints returning *"Upgrade to GitHub Pro or make this
repository public to enable this feature"* — no longer applies. Confirm with:

```bash
gh repo view Sdomit/Planarus --json visibility
```

**`main` still has no required status checks until the ruleset below is
applied, and the practical effect is worse than "unprotected".** `gh pr merge
--auto` does not wait for CI when there is no required check to wait *for* — it
merges on the spot. That is how #135 merged while all four jobs were still
queued. Until the ruleset lands, polling `gh pr checks` and merging only on four
greens is the only gate that exists, and it is a habit rather than a control.

## Ready to apply — the four required checks

Nothing gates this any more; it is the whole change. The contexts are the job
names exactly as GitHub reports them; a typo creates a required check that
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
          { "context": "Web (vitest + typecheck + lint + build)" } ] } }
  ]
}
JSON
```

**This ruleset requires that every pull request produce a CI run**, which is why
[.github/workflows/ci.yml](../.github/workflows/ci.yml) no longer carries `paths`
filters. It used to skip `**.md`, `docs/**` and `context/**` to conserve metered
Actions minutes on the private repo; public repositories are not metered, so the
saving is gone and the hazard is not. A filtered-out event produces no run at
all, so a docs-only pull request would leave all four contexts permanently
pending and could never merge. Do not reintroduce the filters without also
adding a skip job that reports those same four context names and exits 0.

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

**Ordering, if this is ever re-applied to a freshly seeded repository:** push
first, *then* POST the ruleset. Applied first, `non_fast_forward` and the
pull-request rule would reject the very push that seeds the repository.

## Main branch — target configuration

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
