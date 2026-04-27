# Normalized review-thread schema

This is the contract between fetcher scripts (`fetch_<provider>.py`) and
all downstream scripts (`filter_active.py`, `render_report.py`,
`update_<provider>.py`). Every fetcher MUST produce JSON that conforms to
this shape on stdout.

The machine-checkable schema lives in
`tests/fixtures/normalized_schema.json` (referenced by
`tests/test_normalize_schema.py` and by `tests/test_fetch_*.py`).

## Thread shape

Each thread is one object in a top-level array. Required fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | `<provider>:<provider-specific-id>`, e.g. `azdo:9876`, `github:PRT_kwDOA...`. |
| `provider` | enum | `azdo`, `github` (v1). `gitlab`, `bitbucket` reserved. |
| `url` | string | Browser-friendly link to the thread. |
| `status` | enum | Normalized: `active`, `pending`, `resolved`. |
| `file` | string | Path relative to repo root. |
| `line` | int | Current line in HEAD. |
| `original_line` | int | Line at the time the comment was posted. |
| `anchor_lost` | bool | True if file no longer exists OR `original_line` past current EOF. |
| `first_comment` | object | `{author, created_at, body}`. |
| `replies` | array | Same shape as `first_comment`, oldest first. |
| `is_bot` | bool | Heuristic: bot-pattern match on `first_comment.author`. Display only — never used to filter. |
| `is_outdated` | bool | Provider says diff position is invalidated. AzDO: always `false`. |
| `raw_status` | string | Provider's pre-normalization status string. Useful for debug/report. |

`additionalProperties: false` — fetchers MUST NOT emit extra fields.

## Status normalization

| Provider raw | Normalized |
|---|---|
| AzDO `active`   | `active` |
| AzDO `pending`  | `pending` |
| AzDO `fixed`    | `resolved` |
| AzDO `closed`   | `resolved` |
| AzDO `byDesign` | `resolved` |
| AzDO `wontFix`  | `resolved` |
| AzDO `unknown`  | `active` (treat conservatively) |
| GitHub `isResolved == true`  | `resolved` |
| GitHub `isResolved == false` | `active` |

## Asymmetries between providers

GitHub has no `pending` state. Consequences:

- A GitHub PR's report will show 0 `pending` in the status counts.
- `pr-review-update --action pending` is unsupported on GitHub in v1
  (write-side is deferred entirely).

This is intentional and documented so a future agent adding GitHub
write-side knows the asymmetry is real.

## PR-level (non-anchored) comments

Out of scope for v1. Fetchers MUST silently exclude them. Optionally a
stderr note that PR-level comments were excluded.
