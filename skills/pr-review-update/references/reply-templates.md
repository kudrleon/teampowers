# Reply text templates

These are the **fixed** reply formats `pr-review-update` posts. The
agent's only input is `--summary`. Changing these formats is a deliberate
version bump, not an in-place edit.

## `--action pending` (with `--summary`)

```
**Addressed in <comma-separated commit short SHAs>**

<summary verbatim>

Marked as pending for reviewer confirmation.
```

## `--action pending --trivial`

```
Trivial fix in <commits>, marking pending.
```

(Reserved for typo fixes and other not-worth-explaining cases. Only
valid with `--action pending`.)

## `--action wontfix` (with `--summary`)

```
**Not fixing in this PR**

<summary verbatim>

Marked won't-fix.
```

## `--action reply-only` (with `--summary`)

```
<summary verbatim>
```

No template footer. Just the agent's words.
