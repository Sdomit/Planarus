# GitHub settings runbook

This runbook covers controls that cannot be committed in a pull request. It
does not authorize a visibility change, release, or licensing change.

## Current state — applied, without the pull-request rule

`Sdomit/Planarus` is **public**, so rulesets are free and the constraint this
section used to describe — both the branch-protection and ruleset REST
endpoints returning *"Upgrade to GitHub Pro or make this repository public to
enable this feature"* — no longer applies.

A ruleset named `main` is **active** on the default branch. Ask what is actually
enforced rather than trusting a ruleset id written down here — deleting and
recreating a ruleset issues a new id, which has already happened once:

```bash
gh api repos/Sdomit/Planarus/rules/branches/main   # the rules in effect, by name
gh api repos/Sdomit/Planarus/rulesets              # the rulesets, with their ids
```

What is enforced is exactly two rules: `deletion` and `non_fast_forward`.
`main` cannot be deleted and cannot be force-pushed (`bypass_actors: []`).

**A gap in coverage is a gap in protection, and it is measured in seconds.**
Replacing this ruleset by deleting it and POSTing a new one leaves an unguarded
window, and one force-push has already landed in exactly such a window — seven
seconds wide, per `gh api repos/Sdomit/Planarus/activity`. Nothing was bypassed;
there was briefly nothing to bypass. Prefer `PUT` on the existing ruleset, which
swaps the rules atomically, over DELETE-then-POST.

The `pull_request` rule from the payload below was dropped deliberately — this
repository does not use pull requests, and that rule would require one for
every change to `main`, with no owner exemption.

**`required_status_checks` is NOT part of it, and must not be added back while
this repository pushes directly to `main`.** It was applied once and had to be
removed within minutes. Required status checks are enforced on direct pushes,
not only on pull-request merges:

```
remote: - 4 of 4 required status checks are expected.
remote: ! [remote rejected] main -> main (push declined due to repository rule violations)
```

That is unsatisfiable here, not merely strict. CI triggers on `push` to `main`
and on `pull_request` (see [ci.yml](../.github/workflows/ci.yml)), so a commit
that has never been pushed to `main` and is not in a pull request has no check
runs attached to it — and it cannot acquire any, because the push that would
start them is the push being rejected. Pushing the branch elsewhere first does
not help: no workflow triggers on other branches. The result is a locked branch
with no path forward except deleting the rule.

The two rules that are active have no such catch. They forbid things rather
than require things, so nothing has to happen first.

**What is therefore not gated.** Nothing stops a direct push to `main` that
breaks CI; the run reports the breakage afterwards. That is the same gap the
note about #135 described from the other side — `gh pr merge --auto` did not
wait for CI because there was no required check to wait for. Only the
`pull_request` rule closes it, and only together with status checks, because it
is the pull request that gives the checks somewhere to run before the merge.
Until then the real gate is running the suite locally before pushing.

## The full payload, for reference

The contexts are the job names exactly as GitHub reports them; a typo creates a
required check that never arrives, which blocks every pull request until the
ruleset is edited. To adopt the pull-request gate later, DELETE the current
existing ruleset's id from `gh api repos/Sdomit/Planarus/rulesets` and `PUT`
this payload onto it. Do not DELETE-then-POST: that opens the unguarded window
described above, and two rulesets both targeting the default branch stack
rather than replace.

Send the body as a file or heredoc via `--input`, not as `-F 'rules[][type]=…'`
flags. The flag form silently produces a different ruleset than intended — it
was tried here and dropped `non_fast_forward` while keeping the rule it was
meant to remove. Read the result back afterwards either way.

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

[.github/workflows/ci.yml](../.github/workflows/ci.yml) no longer carries
`paths` filters, and adopting the pull-request rule depends on that. The filters
used to skip `**.md`, `docs/**` and `context/**` to conserve metered Actions
minutes on the private repo; public repositories are not metered, so the saving
is gone and the hazard is not. A filtered-out event produces no run at all, so
with the pull-request rule on, a docs-only pull request would leave all four
contexts permanently pending and could never merge. Do not reintroduce the
filters without also adding a skip job that reports those same four context
names and exits 0.

Decisions baked into that payload, each deliberate:

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

Items 2, 4, 5 and 6 stand. Item 1 is the open question and item 3 only matters
once item 1 is taken:

1. **Not adopted.** Requiring pull requests, the full CI suite, up-to-date
   branches and resolved conversations is what the omitted `pull_request` rule
   does. Revisit if a second contributor arrives, or if a bad direct push to
   `main` ever costs more than the workflow does.
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
