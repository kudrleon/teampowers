# Error contract

## General rules (every script in this plugin)

- **Exit code:** 0 on success, non-zero on failure.
- **Stdout:** primary data only. JSON for fetchers/filter; markdown for
  the renderer.
- **Stderr:** diagnostics only. On failure, structured JSON:

  ```json
  {
    "error":   "<machine-readable code>",
    "message": "<human-readable explanation>",
    "fix":     "<actionable suggestion or null>"
  }
  ```
- Stdout and stderr never carry the same channel of information.

## Error code enum

### Context detection
- `unsupported_provider`
- `no_pr_for_branch`
- `multiple_prs_for_branch` — payload also includes `multiple_prs: [...]`
  in the success-shaped JSON on stdout (not stderr) so the agent can ask
  the user to pick.

### Auth
- `azdo_not_logged_in`
- `azdo_pat_invalid`
- `azdo_api_failure`
- `github_not_authed`
- `github_api_failure`

### `pr-review-update` specific
- `thread_not_found`
- `thread_already_pending` — soft no-op, exit 0, warning on stderr.
- `thread_already_resolved` — soft no-op, exit 0, warning on stderr.
- `git_evidence_file_unchanged` — hard block, exit non-zero.
- `git_evidence_line_unchanged` — warn, exit non-zero unless
  `--force-line-unchanged` was passed.
- `github_write_unsupported_v1` — provider mismatch.

### Generic
- `working_tree_dirty` — diagnostic only on stderr, never blocks.
- `usage` — invalid CLI arguments.
