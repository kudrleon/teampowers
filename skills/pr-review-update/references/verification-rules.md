# Git evidence verification rules

`pr-review-update --action pending` MUST NOT post unless the named
commits actually changed the thread's file. This is the only thing
that prevents the `pending` flag from drifting into "Claude said done."

## Two checks

### 1. file-changed (HARD BLOCK on failure)

For each commit in `--commits`, check whether it touched the thread's
file. If none did, the verifier emits:

```json
{"error": "git_evidence_file_unchanged", "message": "...", "fix": "..."}
```

…and exits non-zero. There is no override for this. Use `--action
wontfix` or `--action reply-only` instead.

### 2. line-range-changed (WARN on failure)

For each commit that touched the file, check whether it touched the
window `original_line ± 5`. If none did, the verifier emits:

```json
{"error": "git_evidence_line_unchanged", "message": "...", "fix": "..."}
```

…and exits with code 2. Override only when a refactor moved the fix
outside the window — pass `--force-line-unchanged`.

## The window constant

The ±5 line window is fixed in `verify_git_evidence.py`'s
`LINE_WINDOW` constant. If experience shows it's wrong, change the
constant in a v1.x patch — DO NOT add a CLI flag for it. (Reasoning:
flags are forever; the right window is a property of the spec, not of
each invocation.)

## Working-tree dirty

If the working tree has uncommitted changes, the verifier emits a
diagnostic on stderr (`working_tree_dirty`) but does NOT block. The
agent is expected to commit before invoking `pr-review-update`. If you
get a hard-block on a fix you "just made," check `git status` first.

## Bogus commit SHA

If none of the named SHAs resolve in this repo, the verifier treats it
as file-unchanged (the SHA could not have touched anything). Hard
block.
