# Changelog

All notable changes to this plugin will be documented here.

## [0.1.0] — 2026-04-26

### Added
- `pr-review-intake` skill: fetch active review threads (AzDO full,
  GitHub read-only), drop `pending`/`resolved`, render markdown report.
- `pr-review-update` skill: post `pending`/`wontfix`/`reply-only` reply
  on a single AzDO thread, with mandatory git-evidence verification for
  `pending`.
- Provider-independent normalized thread schema (see
  `skills/pr-review-intake/references/normalized-schema.md`).
- Reference docs: `auth.md`, `errors.md`, `adding-providers.md`,
  `verification-rules.md`, `reply-templates.md`.
- CI: `pytest` + manifest validation on every PR.

### Known limitations (deferred)
- GitHub write-side (`pr-review-update`) — v1.1.
- PR-level (non-anchored) comments — out of scope.
- Resolving threads (`active → resolved`) — reviewer territory.
- Batch mode for `pr-review-update` — out of scope.
