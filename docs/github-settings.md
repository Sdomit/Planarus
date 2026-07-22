# GitHub settings runbook

This runbook covers controls that cannot be committed in a pull request. It
does not authorize a visibility change, release, or licensing change.

## Current constraint — 22 July 2026

Planarus is private. GitHub's branch-protection and ruleset REST endpoints
currently return: **"Upgrade to GitHub Pro or make this repository public to
enable this feature."** No repository-protection setting was changed by this
hardening branch.

The owner must choose one of these paths before enforcing the controls below:

1. Keep Planarus private and upgrade the account to GitHub Pro (or move it to
   an eligible Team/Enterprise plan).
2. Make the repository public only after completing the OSS-launch privacy and
   release review.
3. Keep the repository private without hosted branch protection for now, while
   using the documented branch-and-PR workflow locally.

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
