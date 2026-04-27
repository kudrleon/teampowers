# `teampowers` tests

## Automated unit tests

From the repo root:

```bash
.venv/bin/pytest -v
```

CI runs the same on PRs (see `.github/workflows/ci.yml`).

The test suite covers:

| Component | What it asserts |
|---|---|
| `filter_active.py` | drop pending/resolved, keep counts, preserve order |
| `render_report.py` | header, anchor-lost, bot, replies, empty cases |
| `_status_map.py` | exhaustive mapping per spec §4.3 |
| `_anchor.py` | missing file, line past EOF, normal cases |
| `fetch_azdo.py` | schema conformance, status mapping, PR-level exclusion, anchor_lost, bot detection, replies order |
| `fetch_github.py` | same as above for GitHub |
| `detect_context.sh` | provider regexes for AzDO HTTPS/SSH, GitHub HTTPS/SSH, unsupported, no-PR |
| `verify_git_evidence.py` | file-unchanged block, line-unchanged warn, anchor-lost, dirty tree, bogus SHA |
| `update_azdo.py` | request method/URL/body shape per action; never PATCHes for reply-only |

Live API calls are NEVER made in unit tests. AzDO uses scrubbed
fixtures replayed against `_call_azdo_api`. GitHub uses scrubbed
fixtures replayed against `_call_github_graphql`. AzDO update mocks
HTTP via the `responses` library.

## Manual smoke test (before tagging a release)

You need a throwaway PR with at least three active comments, one
`pending`, and one `resolved`.

1. `git checkout <branch with the test PR>`
2. `/pr-review-intake` — verify the report shows correct counts and
   correct active-thread list.
3. Make a small commit addressing one thread.
4. `/pr-review-update --thread <id> --commits HEAD --summary "smoke test"` —
   verify the reply appears on the PR and the status flips to `pending`.
5. `/pr-review-update --thread <other-id> --commits HEAD --summary "..."` —
   on a thread whose file you DID NOT touch. Verify hard-block.
6. `/pr-review-update --thread <other-id> --action wontfix --summary "..."` —
   verify it goes through without verification, sets `wontFix` status,
   and posts the wontfix template.
7. Re-run `/pr-review-intake`. Verify the addressed threads are now in
   counts, not the active list.

End-to-end automated tests against a live PR are intentionally out of
scope for v1 — too brittle, requires creds.
