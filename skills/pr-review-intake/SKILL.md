---
name: pr-review-intake
description: Use when the user explicitly invokes /pr-review-intake, asks the skill by name, or gives a clear and specific instruction to fetch the current PR's open review comments (e.g. "pull the open review threads for this branch", "show me unaddressed AzDO review comments"). Do NOT trigger on general talk about PRs, reviews, or comments. Supports Azure DevOps fully and GitHub read-only in v1.
---

# pr-review-intake

Fetch active review threads from the current branch's PR, drop the ones
that are already deliberately addressed (`pending` / `resolved`), and
present the rest to you for evaluation via `superpowers`.

This skill **does not inspect code, does not write to the provider, and
does not auto-invoke any other skill.** All cognition is delegated.

## When to use

- User typed `/pr-review-intake` or asked the skill by name.
- User explicitly asked for the current PR's open review comments.

**Do NOT trigger** on general talk about reviews, comments, or PRs —
even if the conversation sounds related. If the user is discussing
review feedback abstractly, ask whether they want to run the skill
before invoking it.

## Steps

1. **Detect context.** Run `bash scripts/detect_context.sh`. It emits
   JSON to stdout on success or structured JSON on stderr on failure
   (see `references/errors.md`).
   - On `unsupported_provider`: tell the user which providers are
     supported and stop.
   - On `no_pr_for_branch`: tell the user no PR exists for this branch
     and stop. **Do NOT offer to create a PR** — out of scope.
   - On `multiple_prs_for_branch`: ask the user which PR (use the list
     in the JSON), then re-run with that PR.

2. **Fetch threads.** Provider-specific:
   - `azdo`:   `python3 scripts/fetch_azdo.py <org> <project> <repo> <pr>`
   - `github`: `python3 scripts/fetch_github.py <owner/repo> <pr>`

   Stdout is a JSON array of normalized threads (see
   `references/normalized-schema.md`). On auth failure, parse the
   stderr JSON and surface its `fix` field to the user verbatim.

3. **Filter.** Pipe the fetcher output:
   `python3 scripts/filter_active.py < <fetcher-output>`.
   Stdout is `{"active": [...], "counts": {...}}`.

4. **Merge context and persist.** Build the persisted shape by adding
   a `"context"` block to the filter output:
   ```json
   {
     "active": [...],
     "counts": {...},
     "context": {
       "provider":         "azdo" | "github",
       "provider_display": "Azure DevOps" | "GitHub",
       "branch":           "<from step 1>",
       "pr_number":        <int>,
       "pr_url":           "<from step 1>",
       "org":     "<azdo only>",
       "project": "<azdo only>",
       "repo":    "<azdo only>"
     }
   }
   ```
   Write to `./docs/pr/<pr_number>-active.json` (mkdir if needed). This
   is the contract for `pr-review-update` (it reads PR coordinates from
   `context` rather than re-detecting). Never inline or skip this step.

5. **Render the report.** Run
   `python3 scripts/render_report.py < ./docs/pr/<pr_number>-active.json`.
   Print the markdown to the conversation.

6. **Hand off.** End with the next-step block already in the report.
   **DO NOT auto-invoke** any other skill.

## Constraints (hard rules)

- ZERO code inspection. The only filesystem read is the `anchor_lost`
  check inside the fetcher.
- NEVER writes to the provider. No replies, no status changes.
- Honors `pending` and `resolved` as deliberate. Never surfaces them in
  the active list.
- Includes `anchor_lost` threads in the active list, flagged. The
  reader decides if the original concern still applies.
- PR-level comments are excluded silently (a stderr note may appear).

## References

- `references/normalized-schema.md` — the JSON contract and status table.
- `references/auth.md` — auth mechanisms and PAT scopes.
- `references/errors.md` — error codes and the stderr-JSON format.
- `references/adding-providers.md` — forward-compat instructions.
