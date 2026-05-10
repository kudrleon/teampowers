# teampowers

Team-workflow companion for [`superpowers`](https://github.com/obra/superpowers).
`teampowers` does **I/O with team systems** (PR providers, branches);
`superpowers` does **cognition** (code inspection, judgment, design,
implementation). Use them together.

## Status

v1 ships:

- **`pr-review-intake`** — pull active review threads from the current
  branch's PR, drop `pending`/`resolved`, hand off to `superpowers`.
  Supports **Azure DevOps** fully and **GitHub** read-only.
- **`pr-review-update`** — after you've addressed a thread in code,
  post a reply and flip the status (`pending` / `wontFix`) with verified
  git evidence. **Azure DevOps** in v1; GitHub write-side coming in v1.1.

GitLab / Bitbucket: not in v1, but the architecture is provider-agnostic
(see `skills/pr-review-intake/references/adding-providers.md`).

## Install

In Claude Code:
```
/plugin install teampowers@<your-handle>
```
(Replace `<your-handle>` with the GitHub user/org hosting this fork.)

## Auth

- **Azure DevOps:** prefers `az login`; falls back to
  `AZURE_DEVOPS_EXT_PAT`. PAT scopes: `Code (read)` for intake,
  `Pull Request Threads (read & write)` for update.
- **GitHub:** prefers `gh auth login`; falls back to `GH_TOKEN`. Scope:
  `repo` (or `public_repo`).

See `skills/pr-review-intake/references/auth.md`.

## Usage

```
$ /pr-review-intake
  → fetches and prints the active threads on this branch's PR

$ /pr-review-update --thread azdo:9876 \
    --commits HEAD --summary "Added null guard on user.session."
  → verifies git evidence, posts reply, flips status to pending
```

**Note on line drift.** Threads are anchored on the comment's *original*
line; the verifier tolerates small drift (±5 lines) automatically. For
larger drift — refactors, file rewrites, deleted lines — `pr-review-update
--action pending` will warn. Re-run with `--force-line-unchanged` and a
`--summary` that explains where the fix moved. Re-running
`/pr-review-intake` refreshes the report but does not loosen the verifier
— that's intentional.

The full design and rationale lives in
`docs/specs/2026-04-26-pr-review-design.md`. The implementation plan
that built this v1 is in `docs/plans/2026-04-26-pr-review-plan.md`.

## Philosophy

Each new skill in `teampowers` must answer ONE question: **does it talk
to team systems, or does it think?** Talking goes here. Thinking goes
to `superpowers`. We will say no to skills that don't fit.

## Roadmap

v1.1 — GitHub write-side for `pr-review-update`.
v2   — `demo-release-branch`, experiment-branch management, other
       team-workflow I/O skills.

## License

MIT — see `LICENSE`.
