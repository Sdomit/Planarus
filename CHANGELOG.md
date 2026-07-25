# Changelog

All notable user-facing release changes will be documented here.

## [Unreleased]

- No public release has been published from the current private repository.
- Release metadata must be synchronized before the first tagged release. The
  API side is now single-sourced: `Settings.app_version` is the one value, and
  `/info`, the OpenAPI document and `apps/api/pyproject.toml` all resolve to it
  (`0.2.0`, enforced by `test_version_single_source`). The npm packages are
  still `0.1.0` (root and web) and are versioned separately — align them when a
  release version is chosen.

## Release policy

Planarus remains pre-1.0 until the owner selects a release version and confirms
the launch, support, and distribution model. Published version numbers are
never reused or silently replaced.
