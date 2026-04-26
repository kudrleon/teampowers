# Design Spec: `teampowers` plugin — `pr-review-intake` and `pr-review-update`

**Status:** Approved design, ready for implementation planning
**Date:** 2026-04-26
**Author:** Leo (with Claude, via `superpowers:brainstorming`)
**Target repo:** new standalone Claude Code plugin repo `teampowers` (NOT the
superpowers fork this design lives in)

---

## 0. Reading this document

This spec is written to be **context-less**: it must stand on its own when
read by a fresh agent in a new repo, with no memory of the brainstorming
session that produced it. Decisions are stated with their reasoning so a
future agent can make consistent calls on edge cases not enumerated here.

**Prerequisites for reading:**
- Familiarity with Claude Code plugins (`.claude-plugin/plugin.json`, skills
  with `SKILL.md` entry points, slash-command invocation).
- Familiarity with the `superpowers` plugin's design — this plugin is a
  deliberate companion to it, with a strict division of labor:
  - `teampowers` does **I/O with team systems** (PR providers, branches).
  - `superpowers` does **cognition** (code inspection, judgment, design,
    implementation).

**Related research:** the original investigation that led to this design
lives in the superpowers fork repo where the brainstorming happened. This
spec supersedes that research's design proposal. The canonical location
for this spec inside the `teampowers` repo is
`docs/specs/2026-04-26-pr-review-design.md`.

---

## 1. Plugin identity and scope

### 1.1 Name and tagline

- **Plugin name:** `teampowers`
- **Tagline:** Team workflow companion for `superpowers`. Handles I/O with
  team systems (pull requests, demo branches, review state) so `superpowers`
  can stay focused on solo-IC cognitive work.

### 1.2 Why a separate plugin (not a contribution to `superpowers`)

The `superpowers` upstream `CLAUDE.md` explicitly rejects domain-specific or
workflow-specific skills, third-party-tool integrations, and skills that
depend on external services. `pr-review-intake` is all of those: it depends
on `gh` and `az` CLIs, it targets a specific workflow (PR review intake),
and it integrates with external services (GitHub, Azure DevOps).

Per `superpowers` guidelines, this kind of skill belongs in its own plugin.
That plugin is `teampowers`.

### 1.3 v1 scope

The first release contains:

- **Plugin scaffold:** `.claude-plugin/plugin.json`, `README.md`, `LICENSE`,
  `.gitignore`, `tests/`, `docs/`.
- **Skill: `pr-review-intake`** (read-side). Fetches active review threads
  from the current branch's PR, filters out deliberately-addressed ones
  (`pending` / `resolved`), and presents the rest to the agent for evaluation
  via `superpowers:receiving-code-review` or `superpowers:brainstorming`.
- **Skill: `pr-review-update`** (write-side). After the agent has addressed
  a thread in code, posts a reply citing the relevant commit(s) and a summary,
  and transitions the thread's status. Verifies real git evidence before
  posting.

Provider support in v1:

- **Azure DevOps:** full support — fetch, filter, report, update.
- **GitHub:** read-only — fetch, filter, report. **No write-side.** Deferred
  to v1.1.
- **GitLab, Bitbucket:** out of scope. Architecture supports adding them
  later via `references/adding-providers.md`.

### 1.4 Out of scope for v1 (explicit non-goals)

To prevent scope creep:

- GitHub write-side (replies, thread resolution).
- PR-level (non-file-anchored) comments.
- Resolving threads (`active → resolved`). Reviewer territory.
- Auto-detection of "what's been fixed since last run."
- Batch mode for `pr-review-update`.
- Creating, opening, or modifying PRs (other than thread status/reply).
- Pushing commits.
- Local caching, "since-last-run" diffs.
- MCP server. May be revisited in v2.
- Code inspection inside the plugin's own scripts. **All judgment is in the
  agent (Claude in the running session) or in delegated `superpowers` skills.**

### 1.5 Future skills (v2+, illustrative)

Not part of v1, but the plugin's identity should leave room for these:

- `demo-release-branch` — assemble a demo/release branch from multiple
  unmerged feature branches.
- Experiment-branch management.
- Other team-workflow I/O skills.

The general rule for what belongs in `teampowers`: **does the skill talk to
team systems, or does it think?** Talking goes here. Thinking goes to
`superpowers`.

---

## 2. Architectural principles

These are the non-negotiable design constraints that shaped the v1 decisions.
A future agent should treat these as project values, not just implementation
notes.

### 2.1 Pure I/O, no cognition

The skills in this plugin **do not inspect code, do not judge whether a
review comment has been addressed, and do not decide what to do about a
comment.** Those are cognitive tasks. They belong to:

- The agent itself (Claude reading the code in the current session).
- `superpowers:receiving-code-review` (per-comment evaluation, pushback,
  per-item implementation).
- `superpowers:brainstorming` (design questions raised by reviewer feedback).
- Other `superpowers` skills (TDD, debugging, etc.).

The plugin's scripts are deterministic: fetch, filter, normalize, post,
verify-git-evidence. No LLM calls from inside the scripts. No clever
heuristics that try to guess intent.

**Why this matters:** Earlier design iterations tried to put classification
heuristics ("file modified since comment → likely_addressed") into the
plugin. They were wrong often enough to be noise, and they duplicated what
the agent can do better in-session with full code context. The clean
boundary is the entire point of having two plugins instead of one mega-skill.

### 2.2 Code is the source of truth, status is a hint

The provider's thread status (`active`, `pending`, `resolved`) is **not
authoritative** for whether a comment has been addressed in code. It's a
human-curated signal that drifts: reviewers forget to mark things resolved,
PR authors mark things `pending` prematurely, code can be fixed without any
status update.

The **code itself**, as inspected by the agent, is what matters.

**The exception:** `pending` and `resolved` are *deliberate* signals — they
were set by a person (or by this plugin's `pr-review-update`, with verified
git evidence). Honor them. Don't second-guess them. The intake skill drops
them from the active list and shows them only as counts.

### 2.3 No local cache, git remote is authoritative

The plugin keeps no persistent state about previous runs. Every invocation is
fresh: pull current threads from the provider, look at current git state,
report. Reproducibility comes from `(remote PR state, current branch HEAD)`
— nothing else.

The one persisted file is `./docs/pr/<pr-number>-active.json`, which is a
*handoff artifact* between intake and downstream skills, not state. It can
be safely deleted at any time; the next intake recreates it.

### 2.4 Provider abstraction must be tested by two real implementations

A schema with one implementation behind it isn't an abstraction; it's a
shape. To prove the schema is genuinely provider-independent, v1 ships two
real provider implementations (AzDO full, GitHub read-only). Adding GitLab
or Bitbucket later should require zero changes to the filter, report, or
verify scripts — only a new `fetch_<provider>.py` and (eventually)
`update_<provider>.py`.

### 2.5 Tight trigger discipline

Skill descriptions explicitly say "Trigger ONLY on explicit invocation."
The plugin should not fire on general talk about PRs, reviews, or comments.
Explicit slash-command invocation, by-name reference, or a clear specific
instruction are the only triggers.

This is deliberate: a skill that fires too eagerly becomes noise, and once
the user starts ignoring its suggestions, the trust is gone.

---

## 3. Repository structure

### 3.1 Repo layout (the `teampowers` GitHub repo, top to bottom)

```
teampowers/                              # git repo root
├── .git/                                # standard git
├── .gitignore                           # see 3.2
├── .github/
│   └── workflows/
│       └── ci.yml                       # lint + unit tests
├── .claude-plugin/
│   └── plugin.json                      # plugin manifest (REQUIRED for plugin discovery)
├── README.md                            # what it is, install, philosophy, roadmap
├── LICENSE                              # match user's preference (likely MIT)
├── CHANGELOG.md
├── skills/
│   ├── pr-review-intake/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── detect_context.sh
│   │   │   ├── fetch_azdo.py
│   │   │   ├── fetch_github.py
│   │   │   ├── filter_active.py
│   │   │   └── render_report.py
│   │   └── references/
│   │       ├── auth.md
│   │       ├── normalized-schema.md
│   │       ├── errors.md
│   │       └── adding-providers.md
│   └── pr-review-update/
│       ├── SKILL.md
│       ├── scripts/
│       │   ├── verify_git_evidence.py
│       │   └── update_azdo.py
│       └── references/
│           ├── verification-rules.md
│           └── reply-templates.md
├── tests/
│   ├── README.md                        # how to run, manual smoke-test instructions
│   ├── fixtures/
│   │   ├── azdo_threads_sample.json     # canned API responses, secrets scrubbed
│   │   ├── github_threads_sample.json
│   │   └── git_repos/                   # tarred fixture repos for verify tests
│   ├── test_filter_active.py
│   ├── test_verify_git_evidence.py
│   ├── test_normalize_schema.py
│   └── test_update_azdo_payload.py      # mocked HTTP, asserts on request body
└── docs/
    └── specs/
        └── 2026-04-26-pr-review-design.md   # this spec
```

### 3.2 `.gitignore`

```
__pycache__/
*.pyc
.DS_Store
.venv/
venv/
.pytest_cache/
/docs/pr/                                # runtime output if the repo is itself a project
```

**Do NOT ignore:**
- `.claude-plugin/` — the plugin manifest must be in version control.
- `skills/` — the actual plugin code.
- `tests/`, `docs/` — development artifacts, but in version control.

### 3.3 `.claude-plugin/plugin.json`

Minimal manifest:

```json
{
  "name": "teampowers",
  "version": "0.1.0",
  "description": "Team workflow companion for superpowers. Handles I/O with team systems (PRs, branches, review state).",
  "author": {
    "name": "<your name>",
    "email": "<your email>"
  }
}
```

(The implementation plan should verify the exact required/allowed fields
against current Claude Code plugin docs.)

### 3.4 What gets shipped vs. what's only in the repo

When a user runs `/plugin install teampowers@<handle>`, Claude Code clones
the entire repo. Only certain things are *runtime-relevant*:

- **Required at runtime:** `.claude-plugin/plugin.json`, `skills/<name>/SKILL.md`,
  and any files SKILL.md references (scripts, references, assets).
- **Ignored at runtime, but kept in repo:** `tests/`, `docs/`, `README.md`,
  `LICENSE`, `CHANGELOG.md`, `.github/`. These are for developers and
  maintainers, not for the agent.

---

## 4. The provider-independent normalized schema

This is the contract that every `fetch_<provider>.py` script must produce.
Downstream scripts (`filter_active.py`, the report renderer, `update_*.py`)
read this shape exclusively.

### 4.1 Thread JSON shape

Each thread is one object:

```json
{
  "id": "azdo:9876",
  "provider": "azdo",
  "url": "https://dev.azure.com/.../discussion/9876",
  "status": "active",
  "file": "src/auth.ts",
  "line": 42,
  "original_line": 40,
  "anchor_lost": false,
  "first_comment": {
    "author": "alice",
    "created_at": "2026-04-22T14:30:00Z",
    "body": "This should handle null values — what if user.session is undefined?"
  },
  "replies": [
    {
      "author": "leo",
      "created_at": "2026-04-22T15:10:00Z",
      "body": "Good point, what about session being undefined?"
    }
  ],
  "is_bot": false,
  "is_outdated": false,
  "raw_status": "active"
}
```

The fetcher's stdout output is a JSON array of these objects.

### 4.2 Field semantics

| Field | Type | Meaning | Notes |
|---|---|---|---|
| `id` | string | Globally unique thread ID, namespaced by provider. Format: `<provider>:<provider-specific-id>`. E.g., `azdo:9876`, `github:PRT_kwDOA...`. Used by `pr-review-update --thread`. | Required |
| `provider` | enum | One of `azdo`, `github`. (`gitlab`, `bitbucket` reserved.) | Required |
| `url` | string | Direct, browser-friendly link to the thread. | Required |
| `status` | enum | Normalized: `active`, `pending`, `resolved`. See 4.3 for mapping. | Required |
| `file` | string | File path the thread is anchored to, relative to repo root. | Required (PR-level threads excluded) |
| `line` | int | Current line number in HEAD. | Required |
| `original_line` | int | Line number at the time the comment was posted (before any rebase/move). | Required |
| `anchor_lost` | bool | True if the file no longer exists, OR the original line is past the file's current end. The fetcher computes this by reading the working tree. | Required |
| `first_comment` | object | The original comment that started the thread. Fields: `author` (string), `created_at` (ISO 8601 UTC), `body` (string). | Required |
| `replies` | array | Subsequent comments on the same thread, oldest first. Empty array if none. Same fields as `first_comment` per entry. | Required |
| `is_bot` | bool | Heuristic: true if `first_comment.author` matches a bot pattern (regex on names like `dependabot[bot]`, `coderabbitai`, `*-bot`, etc.). For display only; never used to filter. | Required |
| `is_outdated` | bool | Provider says the diff position is invalidated. GitHub: `isOutdated`. AzDO: always `false` (no equivalent). | Required |
| `raw_status` | string | The provider's actual status string before normalization. Useful for debug/report. E.g., `active`, `pending`, `fixed`, `byDesign`, `wontFix`, `closed`, `unknown`, `resolved-true`, `resolved-false`. | Required |

### 4.3 Status normalization table

| Provider raw status | Normalized `status` |
|---|---|
| AzDO `active` | `active` |
| AzDO `pending` | `pending` |
| AzDO `fixed` | `resolved` |
| AzDO `closed` | `resolved` |
| AzDO `byDesign` | `resolved` |
| AzDO `wontFix` | `resolved` |
| AzDO `unknown` | `active` (treat conservatively) |
| GitHub `isResolved == true` | `resolved` |
| GitHub `isResolved == false` | `active` |
| GitHub (no `pending` equivalent in v1) | (never produced) |

### 4.4 Asymmetries between providers

GitHub has no `pending` state. This means:

- GitHub threads, in the intake report, will only ever be counted as
  `active` or `resolved`.
- The "X pending" count in the report's status summary will be 0 for GitHub
  PRs.
- `pr-review-update`'s `--action pending` flow is unsupported on GitHub in
  v1 (write-side is deferred entirely).

This is documented in `references/normalized-schema.md` so a future agent
adding GitHub write-side knows the asymmetry is real and intentional.

### 4.5 PR-level (non-anchored) comments

Out of scope for v1. If a fetcher encounters a non-anchored PR-level
comment, it should:

- Skip it silently (do not include it in the array).
- Optionally log a stderr warning that PR-level comments were excluded.

This keeps the schema simple (file/line are always required) and matches
the fact that the round-trip ("addressed in code, marked pending") doesn't
naturally apply to general PR comments.

---

## 5. Skill: `pr-review-intake`

### 5.1 Purpose

Fetch active review threads for the current branch's PR, drop the ones
that are already deliberately addressed (`pending` / `resolved`), and
present the rest to the agent for evaluation via `superpowers`.

This skill **does not inspect code, does not write to the provider, and
does not auto-invoke any downstream skill.**

### 5.2 SKILL.md frontmatter

```yaml
---
name: pr-review-intake
description: Pull active review threads for the current branch's PR and prepare
  them for handoff to superpowers. Trigger ONLY when the user explicitly invokes
  it — by slash command (/pr-review-intake), by name ("run pr-review-intake",
  "use teampowers pr-review-intake"), or by a clear and specific instruction to
  fetch the current PR's review comments ("pull the open review threads from
  Azure DevOps for this branch"). Do NOT auto-trigger on general talk about
  PRs, reviews, or comments — even if it sounds related. If the user is
  discussing review feedback abstractly, ask whether they want to run the skill
  before invoking it. Supports Azure DevOps fully and GitHub read-only in v1;
  if the provider is unsupported, say so and stop.
---
```

### 5.3 Process flow

1. **Detect context.** Run `scripts/detect_context.sh`. Returns JSON:
   ```json
   {
     "provider": "azdo|github|unsupported",
     "branch": "feature/auth-refactor",
     "repo": "...",
     "org": "...",      // azdo only
     "project": "...",  // azdo only
     "pr_number": "1234" | null,
     "pr_url": "https://..." | null,
     "multiple_prs": [<list>] | null  // present if branch matches >1 active PR
   }
   ```
   - If `provider == "unsupported"`: print supported list, exit non-zero.
   - If `pr_number == null`: tell user no PR exists for this branch, exit
     non-zero. **Do NOT offer to create one** (out of scope).
   - If `multiple_prs` is non-empty: ask the user which PR (interactive
     choice). Re-run the rest of the flow with the chosen `pr_number`.

2. **Fetch threads.** Provider-specific:
   - `azdo`: `python3 scripts/fetch_azdo.py <org> <project> <repo> <pr>`
   - `github`: `python3 scripts/fetch_github.py <owner/repo> <pr>`
   - Stdout: JSON array of normalized threads (schema in §4).
   - On failure: stderr structured JSON error, non-zero exit (see §8).

3. **Filter.** `python3 scripts/filter_active.py < <fetcher-output>`:
   - Drops threads where `status in ("pending", "resolved")`.
   - Outputs object:
     ```json
     {
       "active": [<full thread objects>],
       "counts": {
         "total": 13,
         "active": 4,
         "pending": 2,
         "resolved": 7
       }
     }
     ```

4. **Persist.** Write the filter output to
   `./docs/pr/<pr_number>-active.json` (create directory if needed). This
   is the contract for downstream skills.

5. **Report.** Run `python3 scripts/render_report.py < <filter-output>`.
   It writes the markdown report to stdout. Print to the conversation.
   Format example in §5.4.

6. **Hand off.** End the report with explicit next-step suggestions. **Do
   NOT auto-invoke** any other skill. The user picks:
   - `/receiving-code-review` — evaluate threads item by item.
   - `/brainstorming` — explore design questions raised by the comments.
   - Or focus on a specific thread first.

### 5.4 Report rendering (`scripts/render_report.py`)

Rendering is implemented imperatively in Python — no template engine, no
external dependencies. The script reads the filter output JSON from stdin
and writes the markdown report to stdout. The report has this shape:

```markdown
# PR #1234 — Active Review Threads

**Provider:** Azure DevOps
**Branch:** feature/auth-refactor
**PR:** https://dev.azure.com/.../pullrequest/1234
**Status counts:** 4 active, 2 pending, 7 resolved (deliberate — not shown)

**Detailed JSON:** `./docs/pr/1234-active.json`

## Active threads

### Thread 1 — `src/auth.ts:42`
- **Author:** alice (2026-04-22T14:30:00Z)
- **Comment:** This should handle null values — what if user.session is undefined?
- **URL:** https://dev.azure.com/.../discussion/9876
- **Thread ID:** `azdo:9876`
- **Replies:** 1 (latest from leo)

### Thread 2 — `src/handlers/login.ts:118` ⚠️ anchor lost
- File no longer exists in the working tree, or the original line is past the file's end.
- **Author:** bob (2026-04-23T09:12:00Z)
- **Comment:** Why are we re-throwing here?
- **URL:** https://dev.azure.com/.../discussion/9881
- **Thread ID:** `azdo:9881`

### Thread 3 — `src/utils/parse.ts:14`
- 🤖 Comment is from a bot (dependabot[bot]).
- **Author:** dependabot[bot] (2026-04-24T03:01:00Z)
- **Comment:** Vulnerable dep flagged.
- **URL:** https://dev.azure.com/.../discussion/9890
- **Thread ID:** `azdo:9890`

---

**Next step:** Pick one:

- `/receiving-code-review` — evaluate each thread, decide which to fix, push
  back where appropriate, implement.
- `/brainstorming` — explore design questions raised by these comments before
  deciding on changes.
- Or pick a specific thread to focus on first.
```

**Per-thread rendering rules:**

- Heading: `### Thread {n} — \`{file}:{line}\`` followed by ` ⚠️ anchor lost`
  if `anchor_lost`.
- If `anchor_lost`: emit a leading bullet explaining what that means.
- If `is_bot`: emit a bot-attribution bullet.
- Always emit the author/comment/url/thread-id bullets in that order.
- If `replies` is non-empty: emit a final bullet with the count and the
  last reply's author.

The trailing "Next step" block is a fixed string literal in the script —
not data-driven.

### 5.5 Constraints (codified in SKILL.md)

- Performs ZERO code inspection. Does not read source files except to
  compute `anchor_lost` (a single existence check + line count).
- Does not WRITE to the provider. No replies, no status changes.
- Honors `pending` and `resolved` as deliberate decisions. Never surfaces
  them in the active list. Only counts.
- Includes `anchor_lost` threads in the active list, flagged. Agent
  decides if the original concern still applies.
- PR-level comments excluded silently.

---

## 6. Skill: `pr-review-update`

### 6.1 Purpose

Post a reply on a single PR review thread citing the commits that
addressed it (or the reasoning if not fixed), and transition the thread's
status. Verify real git evidence before posting `--action pending`.

### 6.2 SKILL.md frontmatter

```yaml
---
name: pr-review-update
description: Mark a single PR review thread as pending after the agent has
  addressed it in code, OR mark it won't-fix with reasoning, OR post a
  reply-only without status change. Trigger ONLY on explicit invocation —
  slash command (/pr-review-update), by name, or a clear specific instruction
  ("mark thread azdo:9876 as pending", "post my fix for thread X", "mark
  thread Y won't-fix"). Do NOT auto-trigger when the agent finishes
  implementing a fix; wait for the user (or the agent acting on prior user
  instruction) to ask. Verifies real git evidence before posting --action
  pending. Supports Azure DevOps in v1; GitHub write-side is deferred to v1.1.
---
```

### 6.3 Invocation contract

```
/pr-review-update
  --thread <id>                              (required)
  [--action pending|wontfix|reply-only]      (default: pending)
  [--commits <sha,sha,...>]                  (default: HEAD; ignored for reply-only)
  (--summary '...' | --trivial)              (one is required, except reply-only must use --summary)
  [--force-line-unchanged]                   (override the line-range warn for --action pending)
```

- `--thread <id>`: required. From the active.json (e.g., `azdo:9876`).
- `--action`: one of three. Defaults to `pending`.
- `--commits`: optional. Defaults to HEAD. Ignored for `reply-only`.
- `--summary`: free-form description. Required unless `--trivial`.
- `--trivial`: escape hatch for typos etc. **Only valid with
  `--action pending`** — won't-fix and reply-only deserve real reasoning,
  not a "trivial" stamp.
- `--force-line-unchanged`: only meaningful for `--action pending`.
  Suppresses the `git_evidence_line_unchanged` warn-and-block when the
  agent has confirmed a refactor moved the fix outside the original line
  window. Has no effect on the file-unchanged hard-block (file-unchanged
  is unconditional for `--action pending`).

### 6.4 Action behavior matrix

| `--action` | File-changed verify | What gets posted | Status flip |
|---|---|---|---|
| `pending` (default) | **Required.** Hard-block on file-unchanged. Warn-and-confirm on line-unchanged. | "Addressed in {{commits}}: {{summary}}. Marked pending for reviewer confirmation." | active → pending |
| `wontfix` | Not required. | "Not fixing in this PR: {{summary}}. Marked won't-fix." | active → wontFix (raw_status = `wontFix`, normalized = `resolved`) |
| `reply-only` | Not required. | `{{summary}}` (free-form, no template footer). | none (stays active) |

### 6.5 Process flow

1. **Resolve the thread.** Read `./docs/pr/<pr>-active.json` to find the
   entry matching `--thread`. If file is missing or thread not found, ask
   the agent to re-run `pr-review-intake` first. (Future improvement: also
   accept a `--metadata-file` arg for callers that have their own JSON.)

2. **Sanity-check the thread's current status** by re-fetching it from
   the provider. If thread's current normalized status is `pending` or
   `resolved`, **soft no-op + warn**: print "thread <id> is already
   <status>, skipping." Exit zero. This makes batch retries safe.

3. **Verify git evidence** — only if `--action pending`. Run
   `scripts/verify_git_evidence.py`:

   - **File-changed check:** Did the thread's file change in the specified
     commits since `first_comment.created_at`?
     - If file did NOT change at all: **HARD BLOCK.** Exit non-zero with
       `git_evidence_file_unchanged`. Tell the agent: "File <path> shows
       no changes between <first_comment.created_at> and HEAD. Refusing to
       mark pending. Investigate, or use --action wontfix or reply-only."
   - **Line-range check:** Did the line range (`original_line ± 5` lines)
     change in those commits? The window is fixed at ±5 in v1; if it
     proves wrong in practice, change the constant in v1.x — do not add
     a CLI flag for it.
     - If file changed but line range did not: **WARN.** Print which
       commits touched the file but not the range, exit non-zero with
       `git_evidence_line_unchanged`. Agent decides: re-run with explicit
       confirmation flag (`--force-line-unchanged`) or pick a different
       action.

   For `--action wontfix` and `reply-only`, skip verification entirely.

4. **Post reply + transition status** via `update_<provider>.py`:
   - **AzDO** (`update_azdo.py`):
     - `POST .../threads/{thread_id}/comments` with the formatted reply body.
     - For `--action pending`: `PATCH .../threads/{thread_id}` with
       `{"status": "pending"}`.
     - For `--action wontfix`: `PATCH` with `{"status": "wontFix"}`.
     - For `--action reply-only`: no PATCH.
   - **GitHub**: not implemented in v1. If invoked on a GitHub thread,
     fail with `github_write_unsupported_v1` and a clear error message.

5. **Report.** Print confirmation: "Thread <id> marked <status>. View: <url>"
   (or "Reply posted on thread <id>. View: <url>" for reply-only.)

### 6.6 Reply text format

The script generates the reply body. Agent's only input is `--summary`.

**`--action pending`** (`--summary` provided):
```
**Addressed in <comma-separated commit short SHAs>**

<summary verbatim>

Marked as pending for reviewer confirmation.
```

**`--action pending --trivial`**:
```
Trivial fix in <commits>, marking pending.
```

**`--action wontfix`**:
```
**Not fixing in this PR**

<summary verbatim>

Marked won't-fix.
```

**`--action reply-only`**:
```
<summary verbatim>
```
(No template footer. Just the agent's words.)

### 6.7 Working-tree assumptions

The verify step inspects committed history. If the working tree is dirty
with uncommitted changes that the agent thinks are the fix, verification
will fail (those commits don't exist).

**Decision:** `pr-review-update` assumes the agent has already committed.
A dirty working tree is not an error. The verify script may emit a
diagnostic stderr line ("note: working tree has uncommitted changes")
but does not block. Agents are expected to commit before invoking this skill.

### 6.8 Constraints (codified in SKILL.md)

- Operates on ONE thread per invocation. No batch mode in v1.
- Hard-block file-unchanged (for `--action pending`). Warn line-unchanged.
- Never marks a thread `resolved` (`fixed`/`closed`/`byDesign`). That's
  reviewer territory. `wontFix` is allowed because it's the PR author's
  call.
- Never posts general PR-level comments. Only comments on existing threads.
- Reply text format is fixed. Agent's only input is `--summary`.
- On API failure: surface the error verbatim, exit non-zero, no retry.

---

## 7. Authentication

### 7.1 Azure DevOps

| Mechanism | When | How |
|---|---|---|
| `az login` (Entra ID) | Default. Interactive dev workstation. | Scripts use `az rest` and inherit the cached session. `detect_context.sh` runs `az account show` first to surface failures early. |
| `AZURE_DEVOPS_EXT_PAT` env var | Fallback. Headless or `az login` failed. | Scripts detect `az account show` failure, look for the env var. If present, use direct `requests` calls with HTTP basic auth `("", $PAT)`. |

PAT scopes (documented in `references/auth.md`):
- `Code (read)` — required for `pr-review-intake`.
- `Pull Request Threads (read & write)` — required for `pr-review-update`.

REST API version: pin `api-version=7.1` in all calls. Document the pin
in scripts. API version bumps must be deliberate code changes.

### 7.2 GitHub

| Mechanism | When | How |
|---|---|---|
| `gh` CLI auth | Default. | Fetcher shells out to `gh api graphql`, inheriting whatever `gh auth status` provides. |
| `GH_TOKEN` env var | Fallback. | `gh` CLI itself respects this — no extra plugin code needed. If `gh auth status` would otherwise fail, the env var takes over. |

PAT scopes: `repo` (or `public_repo` for public-only). Documented in
`references/auth.md`.

### 7.3 Auth failure handling

Every script does an early auth check. On failure:

- Exit non-zero.
- Write structured JSON to stderr:
  ```json
  {
    "error": "azdo_not_logged_in",
    "message": "az account show failed and AZURE_DEVOPS_EXT_PAT is not set",
    "fix": "Run: az login --use-device-code, OR export AZURE_DEVOPS_EXT_PAT=<your-pat>"
  }
  ```
- SKILL.md instructs the agent to parse the stderr JSON and surface `fix`
  to the user.

No silent recovery. No retry chains. No fallback between mechanisms beyond
the single layered `az login → PAT` and `gh CLI → GH_TOKEN` paths.

---

## 8. Error contract

### 8.1 General rules for every script in the plugin

- **Exit code:** 0 on success, non-zero on failure.
- **Stdout:** primary data output only (e.g., normalized JSON for fetchers,
  filter output for `filter_active.py`).
- **Stderr:** diagnostics only. On failure, structured JSON:
  ```json
  {
    "error": "<machine-readable-code>",
    "message": "<human-readable-explanation>",
    "fix": "<actionable-suggestion-or-null>"
  }
  ```
- Never mix data and diagnostics on the same stream.

### 8.2 Error codes (enumerated in `references/errors.md`)

Context detection:
- `unsupported_provider`
- `no_pr_for_branch`
- `multiple_prs_for_branch` — accompanied by a list in the JSON for the
  agent to present to the user.

Auth:
- `azdo_not_logged_in`
- `azdo_pat_invalid`
- `azdo_api_failure`
- `github_not_authed`
- `github_api_failure`

`pr-review-update` specific:
- `thread_not_found`
- `thread_already_pending` — soft no-op, exit zero, warning on stderr.
- `thread_already_resolved` — soft no-op, exit zero, warning on stderr.
- `git_evidence_file_unchanged` — hard block, exit non-zero.
- `git_evidence_line_unchanged` — warn-and-confirm, exit non-zero unless
  `--force-line-unchanged` is passed.
- `github_write_unsupported_v1` — provider mismatch.

Generic:
- `working_tree_dirty` — diagnostic only, never blocks.

---

## 9. Adding a new provider (forward-compatibility)

To add GitLab, Bitbucket, or another provider in v2+:

1. Add a `case` to `detect_context.sh` matching the remote URL pattern.
   Extract whatever identifiers the provider's APIs need.
2. Write `fetch_<provider>.py`. Output the normalized schema (§4)
   exactly. Lean on the provider's CLI if one exists (`glab` for GitLab)
   to avoid handling tokens directly.
3. Map the provider's status concepts to `{active, pending, resolved}`.
   Document any asymmetry (e.g., GitLab discussions have `resolved` boolean
   only; Bitbucket has `state ∈ {OPEN, RESOLVED}`).
4. If the provider doesn't have a `pending`-equivalent status, document
   that fact and either omit `pr-review-update --action pending` for that
   provider or map `pending` to a custom resolved-with-tag state.
5. Write `update_<provider>.py` for write-side. Implement the three
   actions: `pending`, `wontfix`, `reply-only`. If the provider lacks
   support for one, fail clearly.
6. **No changes** to `filter_active.py`, the report template, or
   `verify_git_evidence.py` should be required.

---

## 10. Testing strategy

### 10.1 Automated tests (in `tests/`)

| Component | Approach | Rationale |
|---|---|---|
| `filter_active.py` | Pure function unit test: feed canned normalized JSON, assert filtered output. | Tiny, critical, dirt cheap. |
| `verify_git_evidence.py` | Run against fixture git repos created in `setUp`. Cover: file-unchanged, line-unchanged-but-file-changed, file-and-line-changed, anchor-lost. | Hard-block gate is security-relevant — bugs cause incorrect replies on real PRs. |
| Status normalization in fetchers | Unit-test the mapping function alone (extract it as a pure function), separately from API calls. | Easy to get the table wrong; trivial to test. |
| Schema conformance | Validate every fetcher's stdout against a JSON schema. | Keeps the abstraction honest. |
| AzDO fetcher API call | Record-and-replay. Fixtures = real AzDO responses with secrets scrubbed. | Avoid live API in tests. |
| GitHub fetcher GraphQL call | Record-and-replay. | Same. |
| `update_azdo.py` POST/PATCH | Mocked HTTP layer (e.g., `responses` library). Assert on request body shape and method. | One mistake here can spam a real PR. |

### 10.2 Manual smoke test (documented in `tests/README.md`)

Before tagging a release:

1. Have a known throwaway PR on a test repo with several active comments,
   at least one `pending`, one `resolved`.
2. Run `/pr-review-intake`. Verify the report shows correct counts and
   correct active-thread list.
3. Make a small commit addressing one thread.
4. Run `/pr-review-update --thread <id> --commits HEAD --summary "test"`.
   Verify the reply appears on the PR and the status flips to `pending`.
5. Run `/pr-review-update` on a thread whose file you didn't touch.
   Verify hard-block.
6. Run with `--action wontfix` on that thread. Verify it goes through
   without verification, sets `wontFix` status, and posts the wontfix
   template.
7. Re-run intake. Verify the addressed threads are now in counts, not
   the active list.

End-to-end automated tests against a live PR are **out of scope** for v1
— too brittle, requires creds.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Skill triggers on general talk about reviews. | Tightened description in SKILL.md frontmatter: "Trigger ONLY on explicit invocation." Same for both skills. |
| `pending` flag becomes meaningless ("Claude said done"). | Hard-gated on `git_evidence_file_unchanged` for `--action pending`. Three explicit `--action` values mean non-fixes can't masquerade as pending. |
| Agent fabricates a commit SHA in `--commits`. | `verify_git_evidence.py` checks that the SHA exists and that it actually touched the file. Bogus SHAs hit `git_evidence_file_unchanged` or fail to resolve. |
| AzDO API surface drifts between API versions. | Pin `api-version=7.1`. Document the pin. Bumps are deliberate code changes. |
| GitHub abstraction is theoretical (no write-side in v1). | Read-only GitHub forces real fetcher and real schema usage. v1.1 adds write-side without touching the abstraction. |
| User runs intake, then changes branch, then runs update. | `pr-review-update` re-fetches the thread to sanity-check current status. The active.json is a hint for thread metadata, not authoritative. |
| Plugin grows into a junk drawer ("teampowers" everything). | Each new skill must answer: I/O with team systems, or judgment? If judgment, it goes to `superpowers`. Documented in `README.md`. |
| Reply text format changes after release. | Reply templates are pinned in §6.6 and `references/reply-templates.md`. Changes are deliberate version bumps. |

---

## 12. End-to-end usage example

(Illustrative — for the implementation plan to validate against.)

```
$ git checkout feature/auth-refactor
$ /pr-review-intake

→ Skill detects: AzDO, org=mycompany, project=backend, repo=api,
  branch=feature/auth-refactor, pr=1234.
→ Fetches 13 threads. Filters: 4 active, 2 pending, 7 resolved.
→ Writes ./docs/pr/1234-active.json.
→ Prints markdown report listing 4 active threads.
→ Suggests next steps: /receiving-code-review or /brainstorming.

$ /receiving-code-review

→ Walks each thread. For thread azdo:9876 (auth.ts:42 — null check):
   reads auth.ts, evaluates the comment, decides reviewer is right,
   implements the fix, runs tests, commits as abc1234.

$ /pr-review-update --thread azdo:9876 --commits abc1234 \
    --summary "Added null guard on user.session; falls back to anonymous user."

→ Reads ./docs/pr/1234-active.json, finds thread.
→ Re-fetches thread status: still 'active'. Proceeds.
→ Verifies: auth.ts changed in abc1234 since 2026-04-22? Yes. Line 42
  region in those changes? Yes. Pass.
→ Posts reply on thread:

    **Addressed in abc1234**

    Added null guard on user.session; falls back to anonymous user.

    Marked as pending for reviewer confirmation.

→ PATCHes thread status to 'pending'.
→ Prints: "Thread azdo:9876 marked pending. View: https://..."

[...repeat for threads 2, 3...]

$ /pr-review-update --thread azdo:9882 --action wontfix \
    --summary "Test exists in auth.integration.test.ts:55, not the unit
               test file the reviewer linked."

→ Skips verification (wontfix doesn't require it).
→ Posts wontfix-formatted reply, PATCHes status to 'wontFix'.
→ Prints confirmation.
```

---

## 13. Implementation plan (next step)

This spec is the input to `superpowers:writing-plans`, which will produce
a step-by-step implementation plan. The plan should:

1. Be executed in the `teampowers` repo (this repo). The spec already
   lives at `docs/specs/2026-04-26-pr-review-design.md`; the plan should
   reference that path, not move or re-copy it.
2. Sequence the work so each chunk is verifiable on its own:
   plugin scaffold → schema + tests → fetchers + tests →
   filter + report + intake SKILL.md → verify + update_azdo + update SKILL.md
   → end-to-end manual smoke test → README + release.
3. Stop at v1 scope. Do not implement GitHub write-side, batch mode,
   wider provider support, or future skills — those are explicitly out of
   scope (§1.4).

---

## 14. Glossary

- **Thread** — a single conversation anchored to a file/line in the PR.
  Contains one or more comments. The unit of work for both skills.
  AzDO uses "thread" natively; GitHub calls them "review threads."
- **Comment** — one message inside a thread. The first comment in a
  thread is the original concern; subsequent comments are replies.
- **Status** (normalized) — `active` (open), `pending` (PR author claims
  fix, awaiting reviewer), `resolved` (reviewer confirmed, or wontFix /
  byDesign / closed).
- **Anchor** — the file + line a thread is attached to. "Anchor lost"
  means the file or line no longer exists in the working tree.
- **Provider** — a code hosting service. v1: `azdo`, `github`.
- **Pending** — workflow state meaning "addressed in code by author,
  awaiting reviewer confirmation." Set by `pr-review-update --action pending`
  with verified git evidence; can also be set manually by the PR author
  outside this plugin.
- **Round-trip** — the workflow `pr-review-intake` → superpowers skill
  (judgment + implementation) → `pr-review-update`. The reason this
  plugin exists.
