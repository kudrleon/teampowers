# Adding a new provider

To add GitLab, Bitbucket, or another provider in v2+:

1. Add a `case` to `detect_context.sh` matching the remote URL pattern.
   Extract whatever identifiers the provider's APIs need.
2. Write `fetch_<provider>.py`. Output the normalized schema (see
   `references/normalized-schema.md`) exactly. Lean on the provider's CLI
   if one exists (`glab` for GitLab) to avoid handling tokens directly.
3. Map the provider's status concepts to `{active, pending, resolved}`.
   Document any asymmetry (e.g., GitLab discussions have `resolved`
   boolean only; Bitbucket has `state ∈ {OPEN, RESOLVED}`).
4. If the provider doesn't have a `pending`-equivalent status, document
   that fact and either omit `pr-review-update --action pending` for that
   provider or map `pending` to a custom resolved-with-tag state.
5. Write `update_<provider>.py` for write-side. Implement the three
   actions: `pending`, `wontfix`, `reply-only`. If the provider lacks
   support for one, fail with a clear error code.

**No changes** to `filter_active.py`, `render_report.py`, or
`verify_git_evidence.py` should be required. If they are, the
abstraction is broken — fix the abstraction, not the consumer.
