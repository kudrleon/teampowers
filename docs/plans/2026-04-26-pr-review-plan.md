# `teampowers` v1 — `pr-review-intake` and `pr-review-update` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `teampowers` Claude Code plugin v1 — two skills (`pr-review-intake`, `pr-review-update`) that bridge Azure DevOps and GitHub PR review threads to the `superpowers` workflow.

**Architecture:** Pure-I/O plugin. Two skills, each a thin SKILL.md plus deterministic Python/bash scripts. Provider-independent normalized JSON schema (§4 of the spec) is the contract between fetchers, filter, render, verify, and update scripts. No code inspection, no LLM calls inside scripts, no local cache. v1 ships full Azure DevOps support and read-only GitHub.

**Tech Stack:** Python 3.11+ (stdlib only for rendering/filtering; `requests` allowed for direct AzDO HTTP when PAT auth is used), `bash` for context detection, `az` CLI (default AzDO auth), `gh` CLI (GitHub auth + GraphQL transport). Tests: `pytest`, `responses` (for HTTP mocking), `jsonschema`. CI: GitHub Actions.

**Spec reference:** Every task below cites a `[Spec §N.N]` anchor. The spec at `docs/specs/2026-04-26-pr-review-design.md` is the source of truth — if anything in this plan contradicts it, the spec wins and the plan is the bug.

**Working tree assumptions:**
- Plan is executed in the existing `teampowers` repo. The repo already contains `README.md`, `LICENSE`, `docs/specs/`, and `docs/research/` (transient).
- Single linear branch `main` is fine — no worktree required.
- Commits are small (per-task), use Conventional Commits style (`feat:`, `test:`, `docs:`, `chore:`).

---

## File map (responsibility per file)

This locks decomposition decisions before tasks begin. Each file has one responsibility; files that change together live together.

### Plugin scaffold (Phase 1)
- `.claude-plugin/plugin.json` — plugin manifest. Single responsibility: declare plugin identity to Claude Code.
- `.gitignore` — exclude build/cache/runtime artifacts.
- `.github/workflows/ci.yml` — CI: lint + unit tests on PRs.
- `pyproject.toml` — declare Python version + test deps; not strictly required for runtime but needed for `pytest` invocation and CI.
- `CHANGELOG.md` — initial v0.1.0 stub.
- `README.md` — already exists; will be expanded in Phase 8.

### Shared schema + helpers (Phase 2)
- `skills/pr-review-intake/references/normalized-schema.md` — human + JSON Schema for the normalized thread shape (§4).
- `tests/conftest.py` — pytest config: ensure `skills/*/scripts/` are importable in tests.
- `tests/fixtures/normalized_schema.json` — JSON Schema file derived from §4.2 + §4.3.
- `tests/fixtures/threads_normalized_sample.json` — canonical normalized JSON used by filter + render tests.
- `tests/test_normalize_schema.py` — validates the sample against the schema.

### Filter (Phase 3)
- `skills/pr-review-intake/scripts/filter_active.py` — pure stdin→stdout filter. Drops `pending`/`resolved`, emits the `{active, counts}` envelope (§5.3 step 3).
- `tests/test_filter_active.py` — feeds canned normalized JSON, asserts envelope shape and counts.

### Renderer (Phase 4)
- `skills/pr-review-intake/scripts/render_report.py` — imperative Python; reads the filter envelope on stdin, emits the markdown report (§5.4).
- `tests/test_render_report.py` — golden-file snapshot tests for active/anchor-lost/bot/replies cases.

### Fetchers (Phase 5)
- `skills/pr-review-intake/scripts/_status_map.py` — pure status-normalization functions (one per provider). Importable, unit-testable.
- `skills/pr-review-intake/scripts/_anchor.py` — pure helper to compute `anchor_lost` from `(file, original_line)` and the working tree.
- `skills/pr-review-intake/scripts/fetch_azdo.py` — AzDO REST fetcher. Calls `az rest` (or `requests` w/ PAT). Maps to normalized schema.
- `skills/pr-review-intake/scripts/fetch_github.py` — GitHub GraphQL fetcher via `gh api graphql`. Maps to normalized schema.
- `tests/test_status_map.py` — exhaustive table-driven test for §4.3.
- `tests/test_anchor.py` — file-missing, line-past-eof, normal cases.
- `tests/fixtures/azdo_threads_sample.json` — scrubbed AzDO API response.
- `tests/fixtures/github_threads_sample.json` — scrubbed GitHub GraphQL response.
- `tests/test_fetch_azdo.py` — mocks `az rest`/`requests`, replays fixture, asserts normalized output validates against schema.
- `tests/test_fetch_github.py` — mocks `gh api graphql`, replays fixture, asserts normalized output validates against schema.

### Context detection + intake SKILL.md (Phase 6)
- `skills/pr-review-intake/scripts/detect_context.sh` — bash. Detects provider from `git remote`, finds PR for current branch, emits the §5.3-step-1 JSON.
- `skills/pr-review-intake/SKILL.md` — entry point. Describes the 6-step flow (§5.3).
- `skills/pr-review-intake/references/auth.md` — auth mechanisms, scopes, fallback (§7).
- `skills/pr-review-intake/references/errors.md` — error code enum (§8.2) + format (§8.1).
- `skills/pr-review-intake/references/adding-providers.md` — forward-compat instructions (§9).
- `tests/test_detect_context.bats` — bats test for `detect_context.sh` against repos faked with environment variables; or, if bats is too heavy, a `tests/test_detect_context.py` that invokes the script via `subprocess` against tmp git repos.
  - **Decision:** use Python+subprocess (avoids extra dependency).

### Verifier (Phase 7)
- `skills/pr-review-update/scripts/verify_git_evidence.py` — given `(file, original_line, first_comment_iso, commit_specs)`, walks `git log` and `git diff` to verify file-changed (hard) and line-range-changed (warn). Pure git CLI usage.
- `skills/pr-review-update/references/verification-rules.md` — explains the file-changed / line-range checks, the ±5 window, and `--force-line-unchanged` semantics (§6.5 step 3).
- `tests/fixtures/git_repos/` — programmatically-built fixture repos (created in test setup, NOT checked in as binaries). Cases: file-unchanged, line-unchanged-but-file-changed, file-and-line-changed, anchor-lost.
- `tests/test_verify_git_evidence.py` — exhaustive coverage of the four cases above + working-tree-dirty diagnostic.

### AzDO updater + update SKILL.md (Phase 8)
- `skills/pr-review-update/scripts/update_azdo.py` — given `(thread, action, summary, commits)`, formats reply per §6.6, posts comment, optionally PATCHes status. Uses `requests` (PAT) or `az rest` (login).
- `skills/pr-review-update/SKILL.md` — entry point. Describes the 5-step flow (§6.5) and the `--action` matrix (§6.4).
- `skills/pr-review-update/references/reply-templates.md` — pinned reply text formats (§6.6).
- `tests/test_update_azdo_payload.py` — uses `responses` library to assert HTTP request method, URL, body shape per action type.

### Manual smoke test + release prep (Phase 9)
- `tests/README.md` — unit-test invocation + manual smoke-test recipe (§10.2).
- `README.md` (expanded) — what it is, install, philosophy, roadmap (§1).

---

## Phase 0 — pre-flight

### Cross-cutting note for implementer subagents — `superpowers:writing-skills`

Tasks that create or edit `SKILL.md` (Tasks 6.6, 8.4) or any
`references/*.md` file (Tasks 2.4, 6.3, 6.4, 6.5, 7.3, 8.3) MUST
invoke `superpowers:writing-skills` BEFORE writing the file.

The plan's drafted text already follows the conventions described
there:

- Frontmatter `description` starts with `Use when…`, names triggering
  conditions only, and DOES NOT summarize the workflow.
- Workflow content (the 6-step / 5-step process, constraints, hard
  rules) lives in the SKILL body, not the frontmatter.
- Reference docs are kept in `references/` per the spec layout — even
  though some are short, the spec's `§3.1` layout treats them as the
  contract surface for forward-compat (`adding-providers.md` etc.).

If the implementer subagent finds a real conflict between the plan's
drafted SKILL/reference text and `superpowers:writing-skills`
guidance, they should follow `writing-skills` AND raise a
DONE_WITH_CONCERNS at the end so the discrepancy gets back into the
spec.

We do NOT subject these SKILL.md files to the `writing-skills`
RED-GREEN-REFACTOR pressure-testing loop. They are invocation-driven
(user types the slash command); they don't enforce a discipline that
needs to resist rationalization. The frontmatter `description` is
the load-bearing part, and that's small enough to verify by review.

### Task 0: Verify clean working state and git config

**Files:** none modified.

- [ ] **Step 1: Confirm we're on `main` with no untracked staged changes**

Run:
```bash
git status
git log --oneline -3
```
Expected: branch `main`, no staged changes. The most recent commit is the spec-add commit `9be0ac1` (or later). The `.claude/` directory and `docs/research/` may be untracked — both are expected.

- [ ] **Step 2: Confirm Python 3.11+ available**

Run: `python3 --version`
Expected: `Python 3.11.x` or higher. If lower, halt and report — the plan assumes 3.11+ for `tomllib`/modern type hints.

- [ ] **Step 3: Confirm test tools are installable**

Run: `python3 -m pip install --dry-run pytest responses jsonschema requests`
Expected: dry-run succeeds. (Actual install happens in Phase 1.)

---

## Phase 1 — plugin scaffold

### Task 1.1: Add `.gitignore`

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.DS_Store
.venv/
venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/
/docs/pr/
```

(Note: `/docs/pr/` is the runtime output path that `pr-review-intake` writes. Excluded so that if the plugin's own repo is itself ever a project under review, we don't accidentally commit the runtime artifact.)

- [ ] **Step 2: Verify nothing previously-tracked is now ignored**

Run: `git status --ignored`
Expected: `__pycache__`, `.venv`, etc. listed under "Ignored files" (or absent if they don't exist). No previously-tracked file disappears from `git ls-files`.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```

---

### Task 1.2: Add `.claude-plugin/plugin.json`

**Files:**
- Create: `.claude-plugin/plugin.json`

**Spec ref:** §3.3.

- [ ] **Step 1: Create the manifest**

```json
{
  "name": "teampowers",
  "version": "0.1.0",
  "description": "Team workflow companion for superpowers. Handles I/O with team systems (PRs, branches, review state).",
  "author": {
    "name": "Leo",
    "email": "kudrleon@gmail.com"
  }
}
```

(If the user prefers a different author block, swap in their values. The spec leaves `<your name>` / `<your email>` as placeholders; this plan uses what we know.)

- [ ] **Step 2: Validate JSON parses**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat: add plugin manifest"
```

---

### Task 1.3: Add `pyproject.toml` for test tooling

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "teampowers-dev"
version = "0.0.0"
description = "Development tooling for the teampowers Claude Code plugin (not packaged or published)."
requires-python = ">=3.11"

[project.optional-dependencies]
test = [
  "pytest>=8.0",
  "responses>=0.25",
  "jsonschema>=4.21",
  "requests>=2.31",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [
  "skills/pr-review-intake/scripts",
  "skills/pr-review-update/scripts",
]
```

(Rationale: this is *dev* tooling only. The runtime scripts call `python3` directly and don't need a packaged install. `pythonpath` lets test files `import filter_active`, `import _status_map`, etc. directly.)

- [ ] **Step 2: Create a virtualenv and install dev deps**

Run:
```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
```
Expected: clean install of pytest, responses, jsonschema, requests.

- [ ] **Step 3: Verify pytest can collect zero tests cleanly**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran in ...s` and exit 5 (pytest's "no tests collected" code) — this is fine for now.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml for dev tooling"
```

---

### Task 1.4: Add `CHANGELOG.md`

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write the stub**

```markdown
# Changelog

All notable changes to this plugin will be documented here.

## [Unreleased]

### Added
- Initial v1 scaffold: `pr-review-intake` and `pr-review-update` skills.
- Azure DevOps full support; GitHub read-only support.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG"
```

---

### Task 1.5: Add CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dev deps
        run: |
          python -m pip install --upgrade pip
          pip install -e '.[test]'
      - name: Validate plugin manifest is valid JSON
        run: python -c "import json; json.load(open('.claude-plugin/plugin.json'))"
      - name: Run pytest
        run: pytest -v
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run pytest and validate manifest on PRs"
```

(The workflow won't run yet — no PR — but it's in place for when one is opened.)

---

## Phase 2 — normalized schema + sample fixture

### Task 2.1: Author the JSON Schema

**Files:**
- Create: `tests/fixtures/normalized_schema.json`
- Create: `tests/conftest.py`

**Spec ref:** §4.1, §4.2, §4.3.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Pytest config — adjust import path for skill scripts."""
# pyproject.toml's `pythonpath` already covers this, but conftest.py
# guarantees the same paths for ad-hoc invocations.
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
for sub in (
    "skills/pr-review-intake/scripts",
    "skills/pr-review-update/scripts",
):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
```

- [ ] **Step 2: Write the JSON Schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "teampowers normalized review thread",
  "type": "array",
  "items": {
    "type": "object",
    "required": [
      "id", "provider", "url", "status",
      "file", "line", "original_line", "anchor_lost",
      "first_comment", "replies",
      "is_bot", "is_outdated", "raw_status"
    ],
    "additionalProperties": false,
    "properties": {
      "id":            { "type": "string", "pattern": "^(azdo|github|gitlab|bitbucket):.+$" },
      "provider":      { "enum": ["azdo", "github", "gitlab", "bitbucket"] },
      "url":           { "type": "string", "format": "uri" },
      "status":        { "enum": ["active", "pending", "resolved"] },
      "file":          { "type": "string", "minLength": 1 },
      "line":          { "type": "integer", "minimum": 0 },
      "original_line": { "type": "integer", "minimum": 0 },
      "anchor_lost":   { "type": "boolean" },
      "is_bot":        { "type": "boolean" },
      "is_outdated":   { "type": "boolean" },
      "raw_status":    { "type": "string" },
      "first_comment": { "$ref": "#/$defs/comment" },
      "replies": {
        "type": "array",
        "items": { "$ref": "#/$defs/comment" }
      }
    }
  },
  "$defs": {
    "comment": {
      "type": "object",
      "required": ["author", "created_at", "body"],
      "additionalProperties": false,
      "properties": {
        "author":     { "type": "string", "minLength": 1 },
        "created_at": { "type": "string", "format": "date-time" },
        "body":       { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py tests/fixtures/normalized_schema.json
git commit -m "test: add normalized-schema JSON Schema and conftest"
```

---

### Task 2.2: Author a canonical normalized sample

**Files:**
- Create: `tests/fixtures/threads_normalized_sample.json`

- [ ] **Step 1: Write the sample**

```json
[
  {
    "id": "azdo:9876",
    "provider": "azdo",
    "url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9876",
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
  },
  {
    "id": "azdo:9881",
    "provider": "azdo",
    "url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9881",
    "status": "active",
    "file": "src/handlers/login.ts",
    "line": 118,
    "original_line": 118,
    "anchor_lost": true,
    "first_comment": {
      "author": "bob",
      "created_at": "2026-04-23T09:12:00Z",
      "body": "Why are we re-throwing here?"
    },
    "replies": [],
    "is_bot": false,
    "is_outdated": false,
    "raw_status": "active"
  },
  {
    "id": "azdo:9890",
    "provider": "azdo",
    "url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9890",
    "status": "active",
    "file": "src/utils/parse.ts",
    "line": 14,
    "original_line": 14,
    "anchor_lost": false,
    "first_comment": {
      "author": "dependabot[bot]",
      "created_at": "2026-04-24T03:01:00Z",
      "body": "Vulnerable dep flagged."
    },
    "replies": [],
    "is_bot": true,
    "is_outdated": false,
    "raw_status": "active"
  },
  {
    "id": "azdo:9891",
    "provider": "azdo",
    "url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9891",
    "status": "pending",
    "file": "src/utils/parse.ts",
    "line": 30,
    "original_line": 30,
    "anchor_lost": false,
    "first_comment": {
      "author": "alice",
      "created_at": "2026-04-22T11:00:00Z",
      "body": "Add a comment explaining why."
    },
    "replies": [],
    "is_bot": false,
    "is_outdated": false,
    "raw_status": "pending"
  },
  {
    "id": "azdo:9892",
    "provider": "azdo",
    "url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9892",
    "status": "resolved",
    "file": "src/utils/parse.ts",
    "line": 45,
    "original_line": 45,
    "anchor_lost": false,
    "first_comment": {
      "author": "alice",
      "created_at": "2026-04-22T11:30:00Z",
      "body": "Typo in the docstring."
    },
    "replies": [],
    "is_bot": false,
    "is_outdated": false,
    "raw_status": "fixed"
  }
]
```

(Five threads: three `active` — one with replies, one with `anchor_lost`, one bot — plus one `pending` and one `resolved`. Used by filter, render, and downstream tests.)

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/threads_normalized_sample.json
git commit -m "test: add canonical normalized threads sample"
```

---

### Task 2.3: Write schema-conformance test

**Files:**
- Create: `tests/test_normalize_schema.py`

- [ ] **Step 1: Write the failing test**

```python
"""Validate the canonical sample fixture against the normalized JSON Schema."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_canonical_sample_validates():
    schema = _load("normalized_schema.json")
    sample = _load("threads_normalized_sample.json")
    Draft202012Validator(schema).validate(sample)


def test_schema_rejects_extra_fields():
    schema = _load("normalized_schema.json")
    sample = _load("threads_normalized_sample.json")
    bad = [dict(sample[0])]
    bad[0]["unexpected_field"] = "nope"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_schema_rejects_wrong_provider():
    schema = _load("normalized_schema.json")
    sample = _load("threads_normalized_sample.json")
    bad = [dict(sample[0])]
    bad[0]["provider"] = "weird-vcs"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/pytest tests/test_normalize_schema.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_normalize_schema.py
git commit -m "test: validate sample against normalized schema"
```

---

### Task 2.4: Author `references/normalized-schema.md`

**Files:**
- Create: `skills/pr-review-intake/references/normalized-schema.md`

**Spec ref:** §4.

- [ ] **Step 1: Write the reference**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-intake/references/normalized-schema.md
git commit -m "docs(intake): add normalized-schema reference"
```

---

## Phase 3 — filter

### Task 3.1: Write failing tests for `filter_active.py`

**Files:**
- Create: `tests/test_filter_active.py`

**Spec ref:** §5.3 step 3.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the filter_active script."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/pr-review-intake/scripts/filter_active.py"
SAMPLE = ROOT / "tests/fixtures/threads_normalized_sample.json"


def run_filter(stdin_text: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_filter_drops_pending_and_resolved():
    out = run_filter(SAMPLE.read_text())
    assert {"active", "counts"} == set(out.keys())
    statuses = [t["status"] for t in out["active"]]
    assert all(s == "active" for s in statuses)
    assert len(out["active"]) == 3


def test_filter_counts_are_correct():
    out = run_filter(SAMPLE.read_text())
    assert out["counts"] == {
        "total": 5,
        "active": 3,
        "pending": 1,
        "resolved": 1,
    }


def test_filter_preserves_order_and_full_thread_objects():
    out = run_filter(SAMPLE.read_text())
    ids = [t["id"] for t in out["active"]]
    assert ids == ["azdo:9876", "azdo:9881", "azdo:9890"]
    assert out["active"][0]["first_comment"]["author"] == "alice"
    assert out["active"][0]["replies"][0]["author"] == "leo"


def test_filter_handles_empty_input():
    out = run_filter("[]")
    assert out == {"active": [], "counts": {"total": 0, "active": 0, "pending": 0, "resolved": 0}}
```

- [ ] **Step 2: Run tests, expect failures**

Run: `.venv/bin/pytest tests/test_filter_active.py -v`
Expected: tests fail because `filter_active.py` doesn't exist yet (likely `FileNotFoundError` from subprocess).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_filter_active.py
git commit -m "test(intake): add failing tests for filter_active"
```

---

### Task 3.2: Implement `filter_active.py`

**Files:**
- Create: `skills/pr-review-intake/scripts/filter_active.py`

- [ ] **Step 1: Implement the script**

```python
#!/usr/bin/env python3
"""Filter normalized threads: drop pending/resolved, emit {active, counts}.

stdin:  JSON array of normalized threads (see references/normalized-schema.md).
stdout: JSON object {"active": [...], "counts": {...}}.
"""
import json
import sys
from collections import Counter


def filter_threads(threads: list[dict]) -> dict:
    counts = Counter(t["status"] for t in threads)
    return {
        "active": [t for t in threads if t["status"] == "active"],
        "counts": {
            "total":    len(threads),
            "active":   counts.get("active", 0),
            "pending":  counts.get("pending", 0),
            "resolved": counts.get("resolved", 0),
        },
    }


def main() -> int:
    threads = json.load(sys.stdin)
    result = filter_threads(threads)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x skills/pr-review-intake/scripts/filter_active.py`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_filter_active.py -v`
Expected: 4 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-intake/scripts/filter_active.py
git commit -m "feat(intake): implement filter_active"
```

---

## Phase 4 — renderer

### Task 4.1: Write failing tests for `render_report.py`

**Files:**
- Create: `tests/test_render_report.py`

**Spec ref:** §5.4.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for render_report.py.

Strategy: pre-filter the canonical sample (so we have the {active,counts}
envelope), augment with the context fields render_report needs (provider
display name, branch, pr_number, pr_url), and snapshot the markdown.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/pr-review-intake/scripts/render_report.py"
SAMPLE = ROOT / "tests/fixtures/threads_normalized_sample.json"


def _filter_envelope() -> dict:
    """Build the {active,counts,...context} payload that render_report eats."""
    threads = json.loads(SAMPLE.read_text())
    active = [t for t in threads if t["status"] == "active"]
    return {
        "active": active,
        "counts": {"total": 5, "active": 3, "pending": 1, "resolved": 1},
        "context": {
            "provider": "azdo",
            "provider_display": "Azure DevOps",
            "branch": "feature/auth-refactor",
            "pr_number": 1234,
            "pr_url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234",
        },
    }


def run_render(payload: dict) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def test_header_lines_present():
    md = run_render(_filter_envelope())
    assert "# PR #1234 — Active Review Threads" in md
    assert "**Provider:** Azure DevOps" in md
    assert "**Branch:** feature/auth-refactor" in md
    assert "**PR:** https://dev.azure.com/example/proj/_git/repo/pullrequest/1234" in md
    assert "**Status counts:** 3 active, 1 pending, 1 resolved" in md
    assert "**Detailed JSON:** `./docs/pr/1234-active.json`" in md


def test_thread_with_replies_shows_latest_replier():
    md = run_render(_filter_envelope())
    # Thread 1 has one reply by leo.
    assert "### Thread 1 — `src/auth.ts:42`" in md
    assert "- **Author:** alice (2026-04-22T14:30:00Z)" in md
    assert "- **Comment:** This should handle null values" in md
    assert "- **URL:** https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9876" in md
    assert "- **Thread ID:** `azdo:9876`" in md
    assert "- **Replies:** 1 (latest from leo)" in md


def test_anchor_lost_thread_renders_warning_and_explanation():
    md = run_render(_filter_envelope())
    assert "### Thread 2 — `src/handlers/login.ts:118` ⚠️ anchor lost" in md
    assert "- File no longer exists in the working tree, or the original line is past the file's end." in md


def test_bot_thread_renders_bot_attribution():
    md = run_render(_filter_envelope())
    assert "### Thread 3 — `src/utils/parse.ts:14`" in md
    assert "- 🤖 Comment is from a bot (dependabot[bot])." in md


def test_empty_active_renders_empty_section():
    payload = _filter_envelope()
    payload["active"] = []
    payload["counts"] = {"total": 2, "active": 0, "pending": 1, "resolved": 1}
    md = run_render(payload)
    assert "## Active threads" in md
    assert "_No active threads._" in md  # see implementation


def test_next_step_block_present():
    md = run_render(_filter_envelope())
    assert "**Next step:** Pick one:" in md
    assert "/receiving-code-review" in md
    assert "/brainstorming" in md
```

- [ ] **Step 2: Run tests, expect failures**

Run: `.venv/bin/pytest tests/test_render_report.py -v`
Expected: failures (script missing).

- [ ] **Step 3: Commit**

```bash
git add tests/test_render_report.py
git commit -m "test(intake): add failing tests for render_report"
```

---

### Task 4.2: Implement `render_report.py`

**Files:**
- Create: `skills/pr-review-intake/scripts/render_report.py`

- [ ] **Step 1: Implement the script**

```python
#!/usr/bin/env python3
"""Render the markdown report for pr-review-intake.

stdin: JSON object {
  "active":   [<thread>, ...],
  "counts":   {"total": N, "active": A, "pending": P, "resolved": R},
  "context":  {
    "provider": "azdo|github",
    "provider_display": "Azure DevOps" | "GitHub",
    "branch": str,
    "pr_number": int,
    "pr_url": str
  }
}
stdout: markdown report (see references/normalized-schema.md and the spec §5.4).
"""
import json
import sys

NEXT_STEPS = """\
**Next step:** Pick one:

- `/receiving-code-review` — evaluate each thread, decide which to fix, push
  back where appropriate, implement.
- `/brainstorming` — explore design questions raised by these comments before
  deciding on changes.
- Or pick a specific thread to focus on first.
"""

ANCHOR_LOST_BULLET = (
    "- File no longer exists in the working tree, or the original line is "
    "past the file's end."
)


def render_thread(index: int, t: dict) -> list[str]:
    lines: list[str] = []
    heading = f"### Thread {index} — `{t['file']}:{t['line']}`"
    if t["anchor_lost"]:
        heading += " ⚠️ anchor lost"
    lines.append(heading)
    if t["anchor_lost"]:
        lines.append(ANCHOR_LOST_BULLET)
    if t["is_bot"]:
        lines.append(f"- 🤖 Comment is from a bot ({t['first_comment']['author']}).")
    lines.append(f"- **Author:** {t['first_comment']['author']} ({t['first_comment']['created_at']})")
    lines.append(f"- **Comment:** {t['first_comment']['body']}")
    lines.append(f"- **URL:** {t['url']}")
    lines.append(f"- **Thread ID:** `{t['id']}`")
    if t["replies"]:
        last_author = t["replies"][-1]["author"]
        lines.append(f"- **Replies:** {len(t['replies'])} (latest from {last_author})")
    lines.append("")  # blank line between threads
    return lines


def render(payload: dict) -> str:
    ctx = payload["context"]
    counts = payload["counts"]
    active = payload["active"]

    lines: list[str] = []
    lines.append(f"# PR #{ctx['pr_number']} — Active Review Threads")
    lines.append("")
    lines.append(f"**Provider:** {ctx['provider_display']}")
    lines.append(f"**Branch:** {ctx['branch']}")
    lines.append(f"**PR:** {ctx['pr_url']}")
    lines.append(
        f"**Status counts:** {counts['active']} active, "
        f"{counts['pending']} pending, "
        f"{counts['resolved']} resolved (deliberate — not shown)"
    )
    lines.append("")
    lines.append(f"**Detailed JSON:** `./docs/pr/{ctx['pr_number']}-active.json`")
    lines.append("")
    lines.append("## Active threads")
    lines.append("")
    if not active:
        lines.append("_No active threads._")
        lines.append("")
    else:
        for i, t in enumerate(active, start=1):
            lines.extend(render_thread(i, t))
    lines.append("---")
    lines.append("")
    lines.append(NEXT_STEPS)
    return "\n".join(lines)


def main() -> int:
    payload = json.load(sys.stdin)
    sys.stdout.write(render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make executable**

Run: `chmod +x skills/pr-review-intake/scripts/render_report.py`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_render_report.py -v`
Expected: 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-intake/scripts/render_report.py
git commit -m "feat(intake): implement render_report"
```

---

## Phase 5 — fetchers

### Task 5.1: Write failing tests for `_status_map`

**Files:**
- Create: `tests/test_status_map.py`

**Spec ref:** §4.3.

- [ ] **Step 1: Write tests**

```python
"""Tests for _status_map: provider raw status -> normalized status."""
import pytest

from _status_map import normalize_azdo, normalize_github


@pytest.mark.parametrize("raw,expected", [
    ("active",   "active"),
    ("pending",  "pending"),
    ("fixed",    "resolved"),
    ("closed",   "resolved"),
    ("byDesign", "resolved"),
    ("wontFix",  "resolved"),
    ("unknown",  "active"),  # spec: treat conservatively
])
def test_normalize_azdo(raw, expected):
    assert normalize_azdo(raw) == expected


@pytest.mark.parametrize("is_resolved,expected", [
    (True,  "resolved"),
    (False, "active"),
])
def test_normalize_github(is_resolved, expected):
    assert normalize_github(is_resolved) == expected


def test_normalize_azdo_unknown_value_defaults_to_active():
    # Future-proofing: any unrecognized value is treated as 'active'.
    assert normalize_azdo("some-future-status") == "active"
```

- [ ] **Step 2: Run, expect failures**

Run: `.venv/bin/pytest tests/test_status_map.py -v`
Expected: import error.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_status_map.py
git commit -m "test(intake): add failing tests for status normalization"
```

---

### Task 5.2: Implement `_status_map.py`

**Files:**
- Create: `skills/pr-review-intake/scripts/_status_map.py`

- [ ] **Step 1: Write it**

```python
"""Provider status normalization.

Pure functions, importable. See references/normalized-schema.md §"Status
normalization" for the table this implements.
"""

_AZDO_MAP = {
    "active":   "active",
    "pending":  "pending",
    "fixed":    "resolved",
    "closed":   "resolved",
    "byDesign": "resolved",
    "wontFix":  "resolved",
    "unknown":  "active",
}


def normalize_azdo(raw: str) -> str:
    """Map an AzDO thread status to {active, pending, resolved}.

    Unknown values are conservatively treated as 'active' so an addressable
    thread is never silently dropped from intake.
    """
    return _AZDO_MAP.get(raw, "active")


def normalize_github(is_resolved: bool) -> str:
    """Map GitHub's `isResolved` boolean to normalized status.

    GitHub has no `pending` equivalent — see references/normalized-schema.md.
    """
    return "resolved" if is_resolved else "active"
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/test_status_map.py -v`
Expected: 10 PASS.

- [ ] **Step 3: Commit**

```bash
git add skills/pr-review-intake/scripts/_status_map.py
git commit -m "feat(intake): implement status normalization"
```

---

### Task 5.3: Write failing tests for `_anchor`

**Files:**
- Create: `tests/test_anchor.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for _anchor.is_anchor_lost."""
import os
from pathlib import Path

import pytest

from _anchor import is_anchor_lost


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "exists.ts").write_text("a\nb\nc\nd\ne\n")  # 5 lines
    return tmp_path


def test_anchor_lost_when_file_missing(tmp_repo):
    assert is_anchor_lost(tmp_repo, "src/missing.ts", original_line=1) is True


def test_anchor_lost_when_line_past_eof(tmp_repo):
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=99) is True


def test_anchor_present_when_line_within_file(tmp_repo):
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=3) is False


def test_anchor_present_when_line_is_exact_eof(tmp_repo):
    # 5-line file; line 5 is valid, line 6 is past EOF.
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=5) is False
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=6) is True


def test_anchor_present_when_line_is_zero():
    # Some providers use 0 to mean "file-level"; spec says PR-level
    # comments are excluded by fetchers, but defensively: line 0 in any
    # existing file is treated as present.
    pass  # behavior unspecified — see spec §4.5; not tested here.
```

- [ ] **Step 2: Run, expect failures**

Run: `.venv/bin/pytest tests/test_anchor.py -v`
Expected: import error.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_anchor.py
git commit -m "test(intake): add failing tests for anchor_lost helper"
```

---

### Task 5.4: Implement `_anchor.py`

**Files:**
- Create: `skills/pr-review-intake/scripts/_anchor.py`

- [ ] **Step 1: Write it**

```python
"""Compute anchor_lost for a thread.

Pure helper — single existence check + line count. The only "code
inspection" the intake skill is allowed to do (spec §5.5).
"""
from pathlib import Path


def is_anchor_lost(repo_root: Path, file: str, original_line: int) -> bool:
    """Return True if `file` no longer exists OR `original_line` is past EOF.

    `repo_root` is the working-tree root the script is invoked from.
    """
    p = repo_root / file
    if not p.is_file():
        return True
    # Count lines without slurping the whole file; small files only matter here.
    with p.open("rb") as f:
        # Add 1 for the trailing newline-or-not; we treat the file as having
        # max(line_count, last-non-empty-line-index) lines.
        lines = sum(1 for _ in f)
    return original_line > lines
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/test_anchor.py -v`
Expected: 4 PASS (one is a pass-through `pass`).

- [ ] **Step 3: Commit**

```bash
git add skills/pr-review-intake/scripts/_anchor.py
git commit -m "feat(intake): implement anchor_lost helper"
```

---

### Task 5.5: Add scrubbed AzDO API fixture

**Files:**
- Create: `tests/fixtures/azdo_threads_sample.json`

- [ ] **Step 1: Author a representative AzDO threads response**

```json
{
  "value": [
    {
      "id": 9876,
      "status": "active",
      "isDeleted": false,
      "lastUpdatedDate": "2026-04-22T15:10:00Z",
      "publishedDate": "2026-04-22T14:30:00Z",
      "threadContext": {
        "filePath": "/src/auth.ts",
        "rightFileStart": { "line": 42, "offset": 1 },
        "rightFileEnd": { "line": 42, "offset": 1 }
      },
      "pullRequestThreadContext": {
        "trackingCriteria": {
          "origLine": 40
        }
      },
      "comments": [
        {
          "id": 1,
          "parentCommentId": 0,
          "author": { "displayName": "alice", "uniqueName": "alice@example.com" },
          "publishedDate": "2026-04-22T14:30:00Z",
          "content": "This should handle null values — what if user.session is undefined?",
          "commentType": "text"
        },
        {
          "id": 2,
          "parentCommentId": 1,
          "author": { "displayName": "leo", "uniqueName": "leo@example.com" },
          "publishedDate": "2026-04-22T15:10:00Z",
          "content": "Good point, what about session being undefined?",
          "commentType": "text"
        }
      ],
      "_links": {
        "self": {
          "href": "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/1234/threads/9876"
        }
      }
    },
    {
      "id": 9881,
      "status": "active",
      "isDeleted": false,
      "publishedDate": "2026-04-23T09:12:00Z",
      "threadContext": {
        "filePath": "/src/handlers/login.ts",
        "rightFileStart": { "line": 118, "offset": 1 },
        "rightFileEnd": { "line": 118, "offset": 1 }
      },
      "pullRequestThreadContext": {
        "trackingCriteria": { "origLine": 118 }
      },
      "comments": [
        {
          "id": 1,
          "parentCommentId": 0,
          "author": { "displayName": "bob", "uniqueName": "bob@example.com" },
          "publishedDate": "2026-04-23T09:12:00Z",
          "content": "Why are we re-throwing here?",
          "commentType": "text"
        }
      ],
      "_links": { "self": { "href": "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/1234/threads/9881" } }
    },
    {
      "id": 9890,
      "status": "active",
      "isDeleted": false,
      "publishedDate": "2026-04-24T03:01:00Z",
      "threadContext": {
        "filePath": "/src/utils/parse.ts",
        "rightFileStart": { "line": 14, "offset": 1 },
        "rightFileEnd": { "line": 14, "offset": 1 }
      },
      "pullRequestThreadContext": { "trackingCriteria": { "origLine": 14 } },
      "comments": [
        {
          "id": 1,
          "parentCommentId": 0,
          "author": { "displayName": "dependabot[bot]", "uniqueName": "dependabot[bot]" },
          "publishedDate": "2026-04-24T03:01:00Z",
          "content": "Vulnerable dep flagged.",
          "commentType": "text"
        }
      ],
      "_links": { "self": { "href": "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/1234/threads/9890" } }
    },
    {
      "id": 9891,
      "status": "pending",
      "isDeleted": false,
      "publishedDate": "2026-04-22T11:00:00Z",
      "threadContext": {
        "filePath": "/src/utils/parse.ts",
        "rightFileStart": { "line": 30, "offset": 1 },
        "rightFileEnd": { "line": 30, "offset": 1 }
      },
      "pullRequestThreadContext": { "trackingCriteria": { "origLine": 30 } },
      "comments": [
        {
          "id": 1,
          "parentCommentId": 0,
          "author": { "displayName": "alice", "uniqueName": "alice@example.com" },
          "publishedDate": "2026-04-22T11:00:00Z",
          "content": "Add a comment explaining why.",
          "commentType": "text"
        }
      ],
      "_links": { "self": { "href": "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/1234/threads/9891" } }
    },
    {
      "id": 9892,
      "status": "fixed",
      "isDeleted": false,
      "publishedDate": "2026-04-22T11:30:00Z",
      "threadContext": {
        "filePath": "/src/utils/parse.ts",
        "rightFileStart": { "line": 45, "offset": 1 },
        "rightFileEnd": { "line": 45, "offset": 1 }
      },
      "pullRequestThreadContext": { "trackingCriteria": { "origLine": 45 } },
      "comments": [
        {
          "id": 1,
          "parentCommentId": 0,
          "author": { "displayName": "alice", "uniqueName": "alice@example.com" },
          "publishedDate": "2026-04-22T11:30:00Z",
          "content": "Typo in the docstring.",
          "commentType": "text"
        }
      ],
      "_links": { "self": { "href": "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/1234/threads/9892" } }
    },
    {
      "id": 9999,
      "status": "active",
      "isDeleted": false,
      "publishedDate": "2026-04-25T08:00:00Z",
      "threadContext": null,
      "comments": [
        {
          "id": 1,
          "parentCommentId": 0,
          "author": { "displayName": "alice", "uniqueName": "alice@example.com" },
          "publishedDate": "2026-04-25T08:00:00Z",
          "content": "General PR-level comment.",
          "commentType": "text"
        }
      ],
      "_links": { "self": { "href": "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/1234/threads/9999" } }
    }
  ],
  "count": 6
}
```

(The last thread, `id: 9999`, is a PR-level comment with `threadContext: null`. The fetcher MUST silently exclude it per §4.5.)

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/azdo_threads_sample.json
git commit -m "test: add scrubbed AzDO threads API fixture"
```

---

### Task 5.6: Write failing tests for `fetch_azdo`

**Files:**
- Create: `tests/test_fetch_azdo.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for fetch_azdo: API response -> normalized JSON.

Mocks the HTTP layer entirely. Asserts on schema validation, status
mapping, PR-level exclusion, anchor_lost computation, and id namespacing.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/azdo_threads_sample.json"
SCHEMA = ROOT / "tests/fixtures/normalized_schema.json"


def _load_schema():
    return Draft202012Validator(json.loads(SCHEMA.read_text()))


@pytest.fixture()
def fake_workspace(tmp_path: Path) -> Path:
    """A working tree with the files referenced by the fixture, sized so
    only thread 9881 is anchor-lost (login.ts missing)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.ts").write_text("\n" * 60)        # 60 lines
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "src" / "utils" / "parse.ts").write_text("\n" * 100)
    # src/handlers/login.ts intentionally missing -> anchor_lost = True
    return tmp_path


def test_fetch_azdo_normalizes_against_schema(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch  # function form, importable
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    _load_schema().validate(threads)


def test_fetch_azdo_excludes_pr_level_comments(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    ids = [t["id"] for t in threads]
    assert "azdo:9999" not in ids       # PR-level comment dropped
    assert ids == [
        "azdo:9876", "azdo:9881", "azdo:9890", "azdo:9891", "azdo:9892",
    ]


def test_fetch_azdo_status_mapping(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["azdo:9876"]["status"]  == "active"
    assert by_id["azdo:9891"]["status"]  == "pending"
    assert by_id["azdo:9892"]["status"]  == "resolved"
    assert by_id["azdo:9892"]["raw_status"] == "fixed"


def test_fetch_azdo_anchor_lost(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["azdo:9881"]["anchor_lost"] is True
    assert by_id["azdo:9876"]["anchor_lost"] is False
    assert by_id["azdo:9890"]["anchor_lost"] is False


def test_fetch_azdo_bot_detection(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["azdo:9890"]["is_bot"] is True
    assert by_id["azdo:9876"]["is_bot"] is False


def test_fetch_azdo_replies_are_oldest_first(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    t = by_id["azdo:9876"]
    assert t["first_comment"]["author"] == "alice"
    assert len(t["replies"]) == 1
    assert t["replies"][0]["author"] == "leo"
```

- [ ] **Step 2: Run, expect failures**

Run: `.venv/bin/pytest tests/test_fetch_azdo.py -v`
Expected: import errors.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_fetch_azdo.py
git commit -m "test(intake): add failing tests for fetch_azdo"
```

---

### Task 5.7: Implement `fetch_azdo.py`

**Files:**
- Create: `skills/pr-review-intake/scripts/fetch_azdo.py`

**Spec ref:** §5.3 step 2, §7.1, §8.

- [ ] **Step 1: Implement the script**

```python
#!/usr/bin/env python3
"""Fetch PR review threads from Azure DevOps and emit normalized JSON.

Usage:
    fetch_azdo.py <org> <project> <repo> <pr_number>

stdout: JSON array of normalized threads (see references/normalized-schema.md).
stderr: structured JSON on failure (see references/errors.md).
exit:   0 on success; non-zero on failure.

Auth: uses `az rest` if available; falls back to direct HTTP with
AZURE_DEVOPS_EXT_PAT (HTTP Basic auth `("", $PAT)`).

API version: pinned to api-version=7.1.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

from _anchor import is_anchor_lost
from _status_map import normalize_azdo

API_VERSION = "7.1"
BOT_PATTERN = re.compile(r"\[bot\]$|^.+-bot$|dependabot|coderabbitai", re.I)


# ----- error reporting ---------------------------------------------------

def _fail(code: str, message: str, fix: str | None = None) -> None:
    json.dump({"error": code, "message": message, "fix": fix}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


# ----- HTTP layer --------------------------------------------------------

def _call_azdo_api(org: str, project: str, repo: str, pr: int) -> dict:
    """Fetch /pullRequests/{pr}/threads. Returns parsed JSON."""
    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/"
        f"{repo}/pullRequests/{pr}/threads?api-version={API_VERSION}"
    )

    # Prefer az rest (inherits Entra ID session); fall back to PAT.
    pat = os.environ.get("AZURE_DEVOPS_EXT_PAT")
    has_az = shutil.which("az") is not None

    if has_az and not pat:
        try:
            proc = subprocess.run(
                ["az", "rest", "--method", "GET", "--url", url],
                capture_output=True, text=True, check=True,
            )
            return json.loads(proc.stdout)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            if "az login" in stderr.lower() or "credentials" in stderr.lower():
                _fail(
                    "azdo_not_logged_in",
                    "az rest failed and AZURE_DEVOPS_EXT_PAT is not set",
                    "Run: az login --use-device-code, OR export AZURE_DEVOPS_EXT_PAT=<your-pat>",
                )
            _fail("azdo_api_failure", f"az rest failed: {stderr}", None)

    if pat:
        resp = requests.get(url, auth=("", pat), timeout=30)
        if resp.status_code in (401, 403):
            _fail("azdo_pat_invalid", f"AzDO returned {resp.status_code}", "Check AZURE_DEVOPS_EXT_PAT scopes (Code: read)")
        if resp.status_code >= 400:
            _fail("azdo_api_failure", f"AzDO HTTP {resp.status_code}: {resp.text[:200]}", None)
        return resp.json()

    _fail(
        "azdo_not_logged_in",
        "Neither az CLI nor AZURE_DEVOPS_EXT_PAT is available",
        "Install az CLI and run `az login`, OR export AZURE_DEVOPS_EXT_PAT=<your-pat>",
    )
    raise AssertionError("unreachable")  # _fail exits


# ----- normalization -----------------------------------------------------

def _is_pr_level(t: dict) -> bool:
    """A thread is PR-level if it has no file/line context."""
    ctx = t.get("threadContext")
    if not ctx:
        return True
    return not ctx.get("filePath")


def _normalize_thread(org: str, project: str, repo: str, pr: int, t: dict, repo_root: Path) -> dict:
    raw_status = t.get("status", "unknown")
    ctx = t["threadContext"]
    file_path = ctx["filePath"].lstrip("/")  # AzDO prefixes with "/"
    line = ctx["rightFileStart"]["line"]
    pr_thread_ctx = (t.get("pullRequestThreadContext") or {})
    tracking = pr_thread_ctx.get("trackingCriteria") or {}
    original_line = tracking.get("origLine", line)

    comments = t.get("comments", [])
    if not comments:
        # AzDO occasionally returns deleted/empty threads. Skip silently.
        return None  # type: ignore[return-value]

    first = comments[0]
    replies = comments[1:]

    def _comment(c: dict) -> dict:
        author = c["author"].get("displayName") or c["author"].get("uniqueName") or "unknown"
        return {
            "author": author,
            "created_at": c["publishedDate"],
            "body": c.get("content", ""),
        }

    is_bot = bool(BOT_PATTERN.search(first["author"].get("displayName", "")))

    # Browser-friendly URL: AzDO PR discussion deep link.
    url = (
        f"https://dev.azure.com/{org}/{project}/_git/{repo}/"
        f"pullrequest/{pr}?discussionId={t['id']}"
    )

    return {
        "id": f"azdo:{t['id']}",
        "provider": "azdo",
        "url": url,
        "status": normalize_azdo(raw_status),
        "file": file_path,
        "line": line,
        "original_line": original_line,
        "anchor_lost": is_anchor_lost(repo_root, file_path, original_line),
        "first_comment": _comment(first),
        "replies": [_comment(c) for c in replies],
        "is_bot": is_bot,
        "is_outdated": False,  # AzDO has no equivalent
        "raw_status": raw_status,
    }


def fetch(org: str, project: str, repo: str, pr: int) -> list[dict]:
    """Programmatic entry-point — used by tests and main()."""
    raw = _call_azdo_api(org, project, repo, pr)
    repo_root = Path.cwd()
    out: list[dict] = []
    for t in raw.get("value", []):
        if t.get("isDeleted"):
            continue
        if _is_pr_level(t):
            sys.stderr.write(f"note: skipped PR-level thread id={t.get('id')}\n")
            continue
        normalized = _normalize_thread(org, project, repo, pr, t, repo_root)
        if normalized is not None:
            out.append(normalized)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        _fail("usage", "fetch_azdo.py <org> <project> <repo> <pr_number>", None)
    org, project, repo, pr_str = argv[1:]
    try:
        pr = int(pr_str)
    except ValueError:
        _fail("usage", f"pr_number must be an integer, got {pr_str!r}", None)
    threads = fetch(org=org, project=project, repo=repo, pr=pr)
    json.dump(threads, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Make executable**

Run: `chmod +x skills/pr-review-intake/scripts/fetch_azdo.py`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_fetch_azdo.py -v`
Expected: 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-intake/scripts/fetch_azdo.py
git commit -m "feat(intake): implement AzDO fetcher"
```

---

### Task 5.8: Add scrubbed GitHub GraphQL fixture

**Files:**
- Create: `tests/fixtures/github_threads_sample.json`

- [ ] **Step 1: Write fixture**

```json
{
  "data": {
    "repository": {
      "pullRequest": {
        "url": "https://github.com/example/repo/pull/1234",
        "headRefName": "feature/auth-refactor",
        "reviewThreads": {
          "nodes": [
            {
              "id": "PRT_kwDOA1",
              "isResolved": false,
              "isOutdated": false,
              "path": "src/auth.ts",
              "line": 42,
              "originalLine": 40,
              "comments": {
                "nodes": [
                  {
                    "author": { "login": "alice" },
                    "createdAt": "2026-04-22T14:30:00Z",
                    "body": "This should handle null values — what if user.session is undefined?",
                    "url": "https://github.com/example/repo/pull/1234#discussion_r1"
                  },
                  {
                    "author": { "login": "leo" },
                    "createdAt": "2026-04-22T15:10:00Z",
                    "body": "Good point, what about session being undefined?",
                    "url": "https://github.com/example/repo/pull/1234#discussion_r2"
                  }
                ]
              }
            },
            {
              "id": "PRT_kwDOA2",
              "isResolved": false,
              "isOutdated": true,
              "path": "src/handlers/login.ts",
              "line": 118,
              "originalLine": 118,
              "comments": {
                "nodes": [
                  {
                    "author": { "login": "bob" },
                    "createdAt": "2026-04-23T09:12:00Z",
                    "body": "Why are we re-throwing here?",
                    "url": "https://github.com/example/repo/pull/1234#discussion_r3"
                  }
                ]
              }
            },
            {
              "id": "PRT_kwDOA3",
              "isResolved": false,
              "isOutdated": false,
              "path": "src/utils/parse.ts",
              "line": 14,
              "originalLine": 14,
              "comments": {
                "nodes": [
                  {
                    "author": { "login": "dependabot[bot]" },
                    "createdAt": "2026-04-24T03:01:00Z",
                    "body": "Vulnerable dep flagged.",
                    "url": "https://github.com/example/repo/pull/1234#discussion_r4"
                  }
                ]
              }
            },
            {
              "id": "PRT_kwDOA4",
              "isResolved": true,
              "isOutdated": false,
              "path": "src/utils/parse.ts",
              "line": 45,
              "originalLine": 45,
              "comments": {
                "nodes": [
                  {
                    "author": { "login": "alice" },
                    "createdAt": "2026-04-22T11:30:00Z",
                    "body": "Typo in the docstring.",
                    "url": "https://github.com/example/repo/pull/1234#discussion_r5"
                  }
                ]
              }
            }
          ]
        }
      }
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/github_threads_sample.json
git commit -m "test: add scrubbed GitHub GraphQL fixture"
```

---

### Task 5.9: Write failing tests for `fetch_github`

**Files:**
- Create: `tests/test_fetch_github.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for fetch_github: GraphQL response -> normalized JSON."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/github_threads_sample.json"
SCHEMA = ROOT / "tests/fixtures/normalized_schema.json"


def _schema():
    return Draft202012Validator(json.loads(SCHEMA.read_text()))


@pytest.fixture()
def fake_workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.ts").write_text("\n" * 60)
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "src" / "utils" / "parse.ts").write_text("\n" * 100)
    # login.ts missing → anchor lost
    return tmp_path


def test_fetch_github_normalizes_against_schema(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    _schema().validate(threads)


def test_fetch_github_status_mapping(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA1"]["status"] == "active"
    assert by_id["github:PRT_kwDOA4"]["status"] == "resolved"
    # GitHub never produces 'pending'
    assert all(t["status"] != "pending" for t in threads)


def test_fetch_github_propagates_is_outdated(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA2"]["is_outdated"] is True
    assert by_id["github:PRT_kwDOA1"]["is_outdated"] is False


def test_fetch_github_anchor_lost_for_missing_file(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA2"]["anchor_lost"] is True


def test_fetch_github_bot_detection(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA3"]["is_bot"] is True
    assert by_id["github:PRT_kwDOA1"]["is_bot"] is False


def test_fetch_github_id_namespacing(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    assert all(t["id"].startswith("github:") for t in threads)
```

- [ ] **Step 2: Run, expect failures**

Run: `.venv/bin/pytest tests/test_fetch_github.py -v`
Expected: import errors.

- [ ] **Step 3: Commit**

```bash
git add tests/test_fetch_github.py
git commit -m "test(intake): add failing tests for fetch_github"
```

---

### Task 5.10: Implement `fetch_github.py`

**Files:**
- Create: `skills/pr-review-intake/scripts/fetch_github.py`

- [ ] **Step 1: Implement**

```python
#!/usr/bin/env python3
"""Fetch PR review threads from GitHub via `gh api graphql`.

Usage:
    fetch_github.py <owner/repo> <pr_number>

stdout: JSON array of normalized threads.
stderr: structured JSON on failure.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _anchor import is_anchor_lost
from _status_map import normalize_github

BOT_PATTERN = re.compile(r"\[bot\]$|^.+-bot$|dependabot|coderabbitai", re.I)

GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $pr: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      url
      headRefName
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          comments(first: 100) {
            nodes {
              author { login }
              createdAt
              body
              url
            }
          }
        }
      }
    }
  }
}
""".strip()


def _fail(code: str, message: str, fix: str | None = None) -> None:
    json.dump({"error": code, "message": message, "fix": fix}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


def _call_github_graphql(owner: str, name: str, pr: int) -> dict:
    if shutil.which("gh") is None:
        _fail("github_not_authed", "gh CLI is not installed",
              "Install gh from https://cli.github.com/, then run `gh auth login`.")
    try:
        proc = subprocess.run(
            [
                "gh", "api", "graphql",
                "-f", f"query={GRAPHQL_QUERY}",
                "-F", f"owner={owner}",
                "-F", f"name={name}",
                "-F", f"pr={pr}",
            ],
            capture_output=True, text=True, check=True,
        )
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        if "authentication" in stderr.lower() or "401" in stderr:
            _fail("github_not_authed", f"gh api failed: {stderr}",
                  "Run: gh auth login   OR set GH_TOKEN.")
        _fail("github_api_failure", f"gh api graphql failed: {stderr}", None)
        raise AssertionError("unreachable")


def _normalize_thread(t: dict, repo_root: Path) -> dict | None:
    if not t.get("path"):
        return None  # skip PR-level (shouldn't happen for reviewThreads, defensive)
    comments = t["comments"]["nodes"]
    if not comments:
        return None
    first = comments[0]
    replies = comments[1:]

    def _c(c: dict) -> dict:
        author = (c.get("author") or {}).get("login") or "unknown"
        return {
            "author": author,
            "created_at": c["createdAt"],
            "body": c.get("body", ""),
        }

    file_path = t["path"]
    original_line = t.get("originalLine") or t.get("line") or 0
    line = t.get("line") or original_line
    is_bot = bool(BOT_PATTERN.search((first.get("author") or {}).get("login", "")))
    url = first.get("url") or ""  # comment URL doubles as thread anchor

    return {
        "id": f"github:{t['id']}",
        "provider": "github",
        "url": url,
        "status": normalize_github(t["isResolved"]),
        "file": file_path,
        "line": line,
        "original_line": original_line,
        "anchor_lost": is_anchor_lost(repo_root, file_path, original_line),
        "first_comment": _c(first),
        "replies": [_c(c) for c in replies],
        "is_bot": is_bot,
        "is_outdated": bool(t.get("isOutdated", False)),
        "raw_status": "isResolved=true" if t["isResolved"] else "isResolved=false",
    }


def fetch(owner_repo: str, pr: int) -> list[dict]:
    if "/" not in owner_repo:
        _fail("usage", f"owner_repo must be 'owner/repo', got {owner_repo!r}", None)
    owner, name = owner_repo.split("/", 1)
    raw = _call_github_graphql(owner, name, pr)
    nodes = (
        raw.get("data", {})
           .get("repository", {})
           .get("pullRequest", {})
           .get("reviewThreads", {})
           .get("nodes", [])
    )
    repo_root = Path.cwd()
    out: list[dict] = []
    for t in nodes:
        normalized = _normalize_thread(t, repo_root)
        if normalized is not None:
            out.append(normalized)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        _fail("usage", "fetch_github.py <owner/repo> <pr_number>", None)
    try:
        pr = int(argv[2])
    except ValueError:
        _fail("usage", f"pr_number must be an integer, got {argv[2]!r}", None)
    threads = fetch(owner_repo=argv[1], pr=pr)
    json.dump(threads, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Make executable**

Run: `chmod +x skills/pr-review-intake/scripts/fetch_github.py`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_fetch_github.py -v`
Expected: 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-intake/scripts/fetch_github.py
git commit -m "feat(intake): implement GitHub fetcher (read-only)"
```

---

## Phase 6 — context detection + intake SKILL.md + references

### Task 6.1: Write failing tests for `detect_context.sh`

**Files:**
- Create: `tests/test_detect_context.py`

**Spec ref:** §5.3 step 1.

- [ ] **Step 1: Write tests**

```python
"""Tests for scripts/detect_context.sh.

Builds throwaway git repos in tmp_path with various remote URLs, runs
the script via subprocess, and asserts on the JSON it emits.

We do NOT exercise the PR-lookup path here (that requires `az` / `gh` and
network). We mock those by setting environment variables the script
checks.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/pr-review-intake/scripts/detect_context.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _init_repo(tmp_path: Path, remote_url: str, branch: str = "feature/x") -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "--initial-branch", branch)
    _git(repo, "remote", "add", "origin", remote_url)
    # Need at least one commit so HEAD exists
    (repo / "f").write_text("hello\n")
    _git(repo, "add", "f")
    _git(repo, "-c", "user.email=test@x", "-c", "user.name=test", "commit", "-m", "init")
    return repo


def _run(repo: Path, env_extra: dict | None = None) -> dict:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "TEAMPOWERS_TEST": "1"}
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(repo), env=env,
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # Caller can still parse stderr JSON when expecting failure.
        return {"_exit": proc.returncode, "_stderr": proc.stderr, "_stdout": proc.stdout}
    return json.loads(proc.stdout)


def test_detects_azdo_remote(tmp_path):
    repo = _init_repo(tmp_path, "https://dev.azure.com/example/proj/_git/repo")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "1234"})
    assert out["provider"] == "azdo"
    assert out["org"] == "example"
    assert out["project"] == "proj"
    assert out["repo"] == "repo"
    assert out["branch"] == "feature/x"
    assert out["pr_number"] == "1234"


def test_detects_azdo_ssh_remote(tmp_path):
    repo = _init_repo(tmp_path, "git@ssh.dev.azure.com:v3/example/proj/repo")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "1234"})
    assert out["provider"] == "azdo"
    assert out["org"] == "example"
    assert out["project"] == "proj"
    assert out["repo"] == "repo"


def test_detects_github_https(tmp_path):
    repo = _init_repo(tmp_path, "https://github.com/example/repo.git")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "777"})
    assert out["provider"] == "github"
    assert out["repo"] == "example/repo"
    assert out["pr_number"] == "777"


def test_detects_github_ssh(tmp_path):
    repo = _init_repo(tmp_path, "git@github.com:example/repo.git")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "777"})
    assert out["provider"] == "github"
    assert out["repo"] == "example/repo"


def test_unsupported_remote(tmp_path):
    repo = _init_repo(tmp_path, "https://gitlab.com/example/repo.git")
    out = _run(repo)
    assert out.get("_exit", 0) != 0
    err = json.loads(out["_stderr"])
    assert err["error"] == "unsupported_provider"


def test_no_pr_for_branch(tmp_path):
    repo = _init_repo(tmp_path, "https://github.com/example/repo.git")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": ""})
    assert out.get("_exit", 0) != 0
    err = json.loads(out["_stderr"])
    assert err["error"] == "no_pr_for_branch"
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv/bin/pytest tests/test_detect_context.py -v`
Expected: failure — script missing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_detect_context.py
git commit -m "test(intake): add failing tests for detect_context.sh"
```

---

### Task 6.2: Implement `detect_context.sh`

**Files:**
- Create: `skills/pr-review-intake/scripts/detect_context.sh`

**Note on test seam:** The script honors a test-only env var `TEAMPOWERS_FAKE_PR` to bypass the network-bound PR lookup. When `TEAMPOWERS_TEST=1` is set, we skip `az`/`gh` invocations entirely and use the fake. This is the only place we add a test seam — the underlying lookup is hard to fake otherwise without bringing in heavy mocking.

- [ ] **Step 1: Implement the script**

```bash
#!/usr/bin/env bash
# Detect provider, branch, PR number for the current repo.
#
# stdout: JSON object (see spec §5.3 step 1).
# stderr: structured JSON on failure (see references/errors.md).
# exit:   0 on success, non-zero on failure.
#
# Test seam:
#   TEAMPOWERS_TEST=1            — skip live az/gh calls
#   TEAMPOWERS_FAKE_PR="1234"    — pretend the lookup returned this PR
#   TEAMPOWERS_FAKE_PR=""        — pretend no PR exists
set -euo pipefail

fail() {
  local code="$1" message="$2" fix="${3:-null}"
  if [[ "$fix" != "null" ]]; then fix="\"$fix\""; fi
  printf '{"error":"%s","message":"%s","fix":%s}\n' \
    "$code" "$message" "$fix" >&2
  exit 1
}

remote_url=$(git config --get remote.origin.url 2>/dev/null || true)
if [[ -z "$remote_url" ]]; then
  fail "unsupported_provider" "no remote.origin.url configured" \
    "Add a git remote pointing to GitHub or Azure DevOps."
fi

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)

provider=""
org=""
project=""
repo=""

# --- Azure DevOps ---
# https://dev.azure.com/<org>/<project>/_git/<repo>
# git@ssh.dev.azure.com:v3/<org>/<project>/<repo>
if [[ "$remote_url" =~ ^https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/.]+)(\.git)?$ ]]; then
  provider="azdo"
  org="${BASH_REMATCH[1]}"
  project="${BASH_REMATCH[2]}"
  repo="${BASH_REMATCH[3]}"
elif [[ "$remote_url" =~ ^git@ssh\.dev\.azure\.com:v3/([^/]+)/([^/]+)/([^/.]+)(\.git)?$ ]]; then
  provider="azdo"
  org="${BASH_REMATCH[1]}"
  project="${BASH_REMATCH[2]}"
  repo="${BASH_REMATCH[3]}"
# --- GitHub ---
# https://github.com/<owner>/<repo>(.git)?
# git@github.com:<owner>/<repo>(.git)?
elif [[ "$remote_url" =~ ^https://github\.com/([^/]+/[^/]+?)(\.git)?$ ]]; then
  provider="github"
  repo="${BASH_REMATCH[1]}"
elif [[ "$remote_url" =~ ^git@github\.com:([^/]+/[^/]+?)(\.git)?$ ]]; then
  provider="github"
  repo="${BASH_REMATCH[1]}"
else
  fail "unsupported_provider" \
    "remote URL not recognized: $remote_url" \
    "Supported: GitHub, Azure DevOps. See references/adding-providers.md."
fi

# --- PR lookup ---
pr_number=""
pr_url=""

if [[ "${TEAMPOWERS_TEST:-}" == "1" ]]; then
  pr_number="${TEAMPOWERS_FAKE_PR-}"
  if [[ -n "$pr_number" ]]; then
    if [[ "$provider" == "github" ]]; then
      pr_url="https://github.com/$repo/pull/$pr_number"
    else
      pr_url="https://dev.azure.com/$org/$project/_git/$repo/pullrequest/$pr_number"
    fi
  fi
elif [[ "$provider" == "github" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    fail "github_not_authed" "gh CLI is not installed" \
      "Install gh from https://cli.github.com/, then run gh auth login."
  fi
  # `gh pr view --json number,url` errors if no PR exists for the branch.
  if pr_json=$(gh pr view --json number,url 2>/dev/null); then
    pr_number=$(printf '%s' "$pr_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["number"])')
    pr_url=$(printf '%s'    "$pr_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["url"])')
  fi
elif [[ "$provider" == "azdo" ]]; then
  if ! command -v az >/dev/null 2>&1; then
    fail "azdo_not_logged_in" "az CLI is not installed" \
      "Install az CLI and run az login."
  fi
  # az repos pr list --status active --source-branch <branch> --org ... --project ... --repository ...
  if pr_json=$(az repos pr list \
        --status active \
        --source-branch "$branch" \
        --org   "https://dev.azure.com/$org" \
        --project "$project" \
        --repository "$repo" \
        --output json 2>/dev/null); then
    count=$(printf '%s' "$pr_json" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')
    if [[ "$count" == "1" ]]; then
      pr_number=$(printf '%s' "$pr_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["pullRequestId"])')
      pr_url="https://dev.azure.com/$org/$project/_git/$repo/pullrequest/$pr_number"
    elif [[ "$count" -gt 1 ]]; then
      multiple=$(printf '%s' "$pr_json" | python3 -c '
import json,sys
prs=json.load(sys.stdin)
print(json.dumps([{"id":p["pullRequestId"],"title":p.get("title","")} for p in prs]))')
      jq_safe=$(printf '%s' "$multiple" | python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin)))')
      printf '{"provider":"%s","branch":"%s","org":"%s","project":"%s","repo":"%s","pr_number":null,"pr_url":null,"multiple_prs":%s}\n' \
        "$provider" "$branch" "$org" "$project" "$repo" "$jq_safe"
      exit 0
    fi
  fi
fi

if [[ -z "$pr_number" ]]; then
  fail "no_pr_for_branch" "no active PR found for branch $branch" \
    "Open a PR for this branch on the provider, then re-run."
fi

# --- emit JSON ---
if [[ "$provider" == "github" ]]; then
  printf '{"provider":"github","branch":"%s","repo":"%s","pr_number":"%s","pr_url":"%s","multiple_prs":null}\n' \
    "$branch" "$repo" "$pr_number" "$pr_url"
else
  printf '{"provider":"azdo","branch":"%s","org":"%s","project":"%s","repo":"%s","pr_number":"%s","pr_url":"%s","multiple_prs":null}\n' \
    "$branch" "$org" "$project" "$repo" "$pr_number" "$pr_url"
fi
```

- [ ] **Step 2: Make executable**

Run: `chmod +x skills/pr-review-intake/scripts/detect_context.sh`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_detect_context.py -v`
Expected: 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-intake/scripts/detect_context.sh
git commit -m "feat(intake): implement detect_context.sh"
```

---

### Task 6.3: Author `references/auth.md`

**Files:**
- Create: `skills/pr-review-intake/references/auth.md`

**Spec ref:** §7.

- [ ] **Step 1: Write reference**

```markdown
# Authentication

This plugin never asks for credentials interactively and never writes
them to disk. It inherits whatever the provider's CLI already has.

## Azure DevOps

| Mechanism | When | How |
|---|---|---|
| `az login` (Entra ID) | Default for interactive workstations. | Scripts call `az rest`, which inherits the cached session. `detect_context.sh` runs `az` early to surface failures. |
| `AZURE_DEVOPS_EXT_PAT` env var | Headless CI, or when `az login` failed. | Scripts detect `az` failure and fall through to direct HTTP with HTTP Basic auth: `("", $PAT)`. |

**PAT scopes required:**
- `Code (read)` — for `pr-review-intake`.
- `Pull Request Threads (read & write)` — for `pr-review-update`.

**API version pin:** all AzDO REST calls pin `api-version=7.1`. Bumps are
deliberate code changes, not silent.

## GitHub

| Mechanism | When | How |
|---|---|---|
| `gh` CLI auth | Default. | Fetcher shells out to `gh api graphql`. |
| `GH_TOKEN` env var | Headless CI, or fallback. | `gh` itself respects `GH_TOKEN` — no extra plugin code needed. |

**PAT scopes required:**
- `repo` (or `public_repo` for public-only).

## Failure handling

Every script emits structured JSON on stderr if auth is missing or
invalid:

```json
{
  "error": "azdo_not_logged_in",
  "message": "az rest failed and AZURE_DEVOPS_EXT_PAT is not set",
  "fix": "Run: az login --use-device-code, OR export AZURE_DEVOPS_EXT_PAT=<your-pat>"
}
```

The SKILL.md instructs the agent to parse this and surface `fix` to the
user verbatim. There is no silent recovery and no retry chain.
```

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-intake/references/auth.md
git commit -m "docs(intake): add auth reference"
```

---

### Task 6.4: Author `references/errors.md`

**Files:**
- Create: `skills/pr-review-intake/references/errors.md`

**Spec ref:** §8.

- [ ] **Step 1: Write reference**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-intake/references/errors.md
git commit -m "docs(intake): add errors reference"
```

---

### Task 6.5: Author `references/adding-providers.md`

**Files:**
- Create: `skills/pr-review-intake/references/adding-providers.md`

**Spec ref:** §9.

- [ ] **Step 1: Write reference**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-intake/references/adding-providers.md
git commit -m "docs(intake): add adding-providers reference"
```

---

### Task 6.6: Author `pr-review-intake/SKILL.md`

**Files:**
- Create: `skills/pr-review-intake/SKILL.md`

**Spec ref:** §5 in full.

- [ ] **Step 1: Write `SKILL.md`**

````markdown
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

4. **Persist.** Write the filter output to
   `./docs/pr/<pr_number>-active.json` (mkdir if needed). This is the
   contract for `pr-review-update`. Never inline or skip this step.

5. **Render the report.** Build the `render_report.py` payload by
   merging the filter output with the context JSON from step 1 (under
   key `"context"`, with fields `provider`, `provider_display` —
   "Azure DevOps" or "GitHub" — `branch`, `pr_number`, `pr_url`).
   Then: `python3 scripts/render_report.py < payload.json`. Print the
   markdown to the conversation.

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
````

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-intake/SKILL.md
git commit -m "feat(intake): add SKILL.md entry point"
```

---

### Task 6.7: End-of-phase smoke test for `pr-review-intake`

**Files:** none modified. Sanity check.

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: every test added so far passes. Count: 4 (filter) + 6 (render) + 10 (status_map) + 4 (anchor) + 6 (fetch_azdo) + 6 (fetch_github) + 6 (detect_context) + 3 (schema) = 45 tests.

- [ ] **Step 2: Manual end-to-end intake against the sample fixture**

Run (from the repo root):
```bash
.venv/bin/python skills/pr-review-intake/scripts/filter_active.py \
  < tests/fixtures/threads_normalized_sample.json \
  | python3 -c '
import json, sys
filt = json.load(sys.stdin)
filt["context"] = {
  "provider": "azdo",
  "provider_display": "Azure DevOps",
  "branch": "feature/auth-refactor",
  "pr_number": 1234,
  "pr_url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234"
}
print(json.dumps(filt))' \
  | .venv/bin/python skills/pr-review-intake/scripts/render_report.py
```
Expected: a markdown report matching the §5.4 example shape — 3 active threads (auth.ts, login.ts ⚠️ anchor lost, parse.ts 🤖 bot), counts "3 active, 1 pending, 1 resolved", trailing next-step block.

- [ ] **Step 3: Commit checkpoint marker (no files)**

```bash
git tag -a phase-6-intake-complete -m "intake skill end-to-end works against fixture data"
```

(If you don't want tags, skip this step. The commits themselves are the audit trail.)

---

## Phase 7 — verifier

### Task 7.1: Write failing tests for `verify_git_evidence`

**Files:**
- Create: `tests/test_verify_git_evidence.py`

**Spec ref:** §6.5 step 3.

- [ ] **Step 1: Write tests**

```python
"""Tests for verify_git_evidence.

Builds throwaway git repos covering the four cases plus working-tree-dirty.
"""
import json
import subprocess
from pathlib import Path

import pytest

from verify_git_evidence import verify

LINE_WINDOW = 5  # spec §6.5 — keep in sync with implementation


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo_factory(tmp_path: Path):
    counter = {"n": 0}
    def make() -> Path:
        counter["n"] += 1
        repo = tmp_path / f"r{counter['n']}"
        repo.mkdir()
        _git(repo, "init", "--initial-branch", "main")
        return repo
    return make


# ----- file-unchanged: HARD BLOCK ----------------------------------------

def test_file_unchanged_returns_block(repo_factory):
    repo = repo_factory()
    (repo / "a.ts").write_text("\n" * 100)
    sha0 = _commit(repo, "init")
    # Make a commit that touches a DIFFERENT file
    (repo / "b.ts").write_text("hello\n")
    sha1 = _commit(repo, "touch b only")

    result = verify(
        repo_root=repo,
        file="a.ts",
        original_line=42,
        first_comment_iso="2020-01-01T00:00:00Z",
        commits=[sha1],
    )
    assert result["status"] == "block"
    assert result["error"] == "git_evidence_file_unchanged"


# ----- file changed but line range untouched: WARN -----------------------

def test_line_range_unchanged_returns_warn(repo_factory):
    repo = repo_factory()
    lines = [f"line{i}\n" for i in range(1, 101)]
    (repo / "a.ts").write_text("".join(lines))
    sha0 = _commit(repo, "init")
    # Modify only line 5 — far from line 42 (window ±5 = 37..47)
    lines[4] = "line5-MODIFIED\n"
    (repo / "a.ts").write_text("".join(lines))
    sha1 = _commit(repo, "touch line 5 only")

    result = verify(
        repo_root=repo,
        file="a.ts",
        original_line=42,
        first_comment_iso="2020-01-01T00:00:00Z",
        commits=[sha1],
    )
    assert result["status"] == "warn"
    assert result["error"] == "git_evidence_line_unchanged"
    assert sha1[:7] in " ".join(result["touched_commits"])


# ----- file and line both changed: PASS ----------------------------------

def test_file_and_line_changed_returns_pass(repo_factory):
    repo = repo_factory()
    lines = [f"line{i}\n" for i in range(1, 101)]
    (repo / "a.ts").write_text("".join(lines))
    sha0 = _commit(repo, "init")
    # Modify line 42 (within window ±5)
    lines[41] = "line42-MODIFIED\n"
    (repo / "a.ts").write_text("".join(lines))
    sha1 = _commit(repo, "touch line 42")

    result = verify(
        repo_root=repo,
        file="a.ts",
        original_line=42,
        first_comment_iso="2020-01-01T00:00:00Z",
        commits=[sha1],
    )
    assert result["status"] == "pass"


# ----- anchor-lost (file deleted in commit): file-changed semantics ------

def test_anchor_lost_file_deleted_passes_file_check(repo_factory):
    """If the file existed in the comment era and was deleted in the commit,
    that counts as the file being changed — verifier should NOT hard-block."""
    repo = repo_factory()
    (repo / "a.ts").write_text("hello\n" * 50)
    _commit(repo, "init")
    (repo / "a.ts").unlink()
    sha1 = _commit(repo, "delete a.ts")
    result = verify(
        repo_root=repo,
        file="a.ts",
        original_line=42,
        first_comment_iso="2020-01-01T00:00:00Z",
        commits=[sha1],
    )
    # File-changed check passes; line check is N/A so falls through to pass
    # (or warn — implementation choice, but MUST NOT be hard-block).
    assert result["status"] in ("pass", "warn")
    assert result.get("error") != "git_evidence_file_unchanged"


# ----- working tree dirty diagnostic -------------------------------------

def test_working_tree_dirty_emits_diagnostic(repo_factory):
    repo = repo_factory()
    lines = [f"line{i}\n" for i in range(1, 101)]
    (repo / "a.ts").write_text("".join(lines))
    sha0 = _commit(repo, "init")
    lines[41] = "line42-MOD\n"
    (repo / "a.ts").write_text("".join(lines))
    sha1 = _commit(repo, "fix line 42")
    # Now dirty the working tree (uncommitted change)
    (repo / "dirt.ts").write_text("uncommitted\n")

    result = verify(
        repo_root=repo,
        file="a.ts",
        original_line=42,
        first_comment_iso="2020-01-01T00:00:00Z",
        commits=[sha1],
    )
    assert result["status"] == "pass"
    assert "working_tree_dirty" in result.get("diagnostics", [])


# ----- bogus SHA ---------------------------------------------------------

def test_bogus_commit_sha_blocks(repo_factory):
    repo = repo_factory()
    (repo / "a.ts").write_text("hello\n")
    _commit(repo, "init")
    result = verify(
        repo_root=repo,
        file="a.ts",
        original_line=1,
        first_comment_iso="2020-01-01T00:00:00Z",
        commits=["deadbeefcafebabe1234567890abcdef12345678"],
    )
    assert result["status"] == "block"
    assert result["error"] == "git_evidence_file_unchanged"
```

- [ ] **Step 2: Run, expect failures**

Run: `.venv/bin/pytest tests/test_verify_git_evidence.py -v`
Expected: import error.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_verify_git_evidence.py
git commit -m "test(update): add failing tests for verify_git_evidence"
```

---

### Task 7.2: Implement `verify_git_evidence.py`

**Files:**
- Create: `skills/pr-review-update/scripts/verify_git_evidence.py`

**Spec ref:** §6.5 step 3, §6.7.

- [ ] **Step 1: Implement**

```python
#!/usr/bin/env python3
"""Verify that the named commits actually addressed a thread.

Two checks:
  1. file-changed (HARD BLOCK on failure):
       did `file` change in any of the named `commits`?
  2. line-range-changed (WARN on failure):
       did the line window `original_line ± LINE_WINDOW` change?

Returns a dict (programmatic) or exits with structured stderr JSON
(CLI). The CLI exit code is:
  - 0       -> pass
  - 2       -> warn (line range unchanged but file changed)
  - 1       -> hard block (file unchanged, or sha bogus)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

LINE_WINDOW = 5  # spec §6.5; change here only (no CLI flag)


# ----- git helpers -------------------------------------------------------

def _git(repo: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _resolve(repo: Path, ref: str) -> str | None:
    rc, out, _ = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return out.strip() if rc == 0 else None


def _commit_touches_file(repo: Path, sha: str, file: str) -> bool:
    rc, out, _ = _git(repo, "show", "--stat", "--format=", "--name-only", sha, "--", file)
    return rc == 0 and bool(out.strip())


def _commit_touches_line_range(
    repo: Path, sha: str, file: str, lo: int, hi: int,
) -> bool:
    """Use `git log -L` to detect changes in a specific line range.

    `git log --no-patch -L<lo>,<hi>:<file> <sha>~1..<sha>` lists commits
    in the range that touched lines [lo, hi]. We just check non-empty.
    """
    parent_rc, _, _ = _git(repo, "rev-parse", "--verify", f"{sha}^")
    range_arg = f"{sha}~1..{sha}" if parent_rc == 0 else sha
    rc, out, _ = _git(
        repo,
        "log", "--no-patch", "--format=%H",
        "-L", f"{lo},{hi}:{file}",
        range_arg,
    )
    if rc != 0:
        # File didn't exist at one end of the range, or line span out of
        # bounds. Conservative: treat as "did not touch the line range."
        return False
    return bool(out.strip())


def _working_tree_dirty(repo: Path) -> bool:
    rc, out, _ = _git(repo, "status", "--porcelain")
    return rc == 0 and bool(out.strip())


# ----- core --------------------------------------------------------------

def verify(
    repo_root: Path,
    file: str,
    original_line: int,
    first_comment_iso: str,
    commits: Iterable[str],
) -> dict:
    """Programmatic entry. Returns:

    {
      "status": "pass" | "warn" | "block",
      "error":  None | "git_evidence_file_unchanged" | "git_evidence_line_unchanged",
      "touched_commits": [<short shas that touched the file>],
      "diagnostics": ["working_tree_dirty"]?,
    }
    """
    diagnostics: list[str] = []
    if _working_tree_dirty(repo_root):
        diagnostics.append("working_tree_dirty")

    resolved: list[str] = []
    for c in commits:
        r = _resolve(repo_root, c)
        if r:
            resolved.append(r)

    # If none of the commits resolve, treat as file-unchanged (bogus SHA).
    touched_file = [
        sha for sha in resolved if _commit_touches_file(repo_root, sha, file)
    ]
    if not touched_file:
        return {
            "status": "block",
            "error":  "git_evidence_file_unchanged",
            "touched_commits": [],
            "diagnostics": diagnostics,
        }

    lo = max(1, original_line - LINE_WINDOW)
    hi = original_line + LINE_WINDOW
    touched_range = [
        sha for sha in touched_file
        if _commit_touches_line_range(repo_root, sha, file, lo, hi)
    ]
    if not touched_range:
        return {
            "status": "warn",
            "error":  "git_evidence_line_unchanged",
            "touched_commits": [sha[:7] for sha in touched_file],
            "diagnostics": diagnostics,
        }

    return {
        "status": "pass",
        "error":  None,
        "touched_commits": [sha[:7] for sha in touched_range],
        "diagnostics": diagnostics,
    }


# ----- CLI ---------------------------------------------------------------

def _emit_stderr(payload: dict) -> None:
    json.dump(payload, sys.stderr)
    sys.stderr.write("\n")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--original-line", required=True, type=int)
    p.add_argument("--first-comment-iso", required=True)
    p.add_argument("--commits", required=True, help="comma-separated")
    p.add_argument("--repo-root", default=os.getcwd())
    args = p.parse_args(argv[1:])

    result = verify(
        repo_root=Path(args.repo_root),
        file=args.file,
        original_line=args.original_line,
        first_comment_iso=args.first_comment_iso,
        commits=[c.strip() for c in args.commits.split(",") if c.strip()],
    )
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    if "working_tree_dirty" in (result.get("diagnostics") or []):
        _emit_stderr({"error": "working_tree_dirty",
                      "message": "working tree has uncommitted changes",
                      "fix": None})
    if result["status"] == "pass":
        return 0
    if result["status"] == "warn":
        _emit_stderr({"error": result["error"],
                      "message": "file changed but line range did not",
                      "fix": "Re-run with --force-line-unchanged if a refactor moved the fix outside the original line window."})
        return 2
    _emit_stderr({"error": result["error"],
                  "message": "file shows no changes between the comment and the named commits",
                  "fix": "Investigate, or use --action wontfix or reply-only."})
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Make executable**

Run: `chmod +x skills/pr-review-update/scripts/verify_git_evidence.py`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_verify_git_evidence.py -v`
Expected: 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-update/scripts/verify_git_evidence.py
git commit -m "feat(update): implement verify_git_evidence"
```

---

### Task 7.3: Author `references/verification-rules.md`

**Files:**
- Create: `skills/pr-review-update/references/verification-rules.md`

- [ ] **Step 1: Write reference**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-update/references/verification-rules.md
git commit -m "docs(update): add verification-rules reference"
```

---

## Phase 8 — AzDO updater + update SKILL.md

### Task 8.1: Write failing tests for `update_azdo`

**Files:**
- Create: `tests/test_update_azdo_payload.py`

**Spec ref:** §6.4, §6.5 step 4, §6.6.

- [ ] **Step 1: Write tests**

```python
"""Tests for update_azdo. Mocks HTTP via the `responses` library."""
import json
import re

import pytest
import responses

from update_azdo import (
    format_reply_body,
    post_update,
    AZDO_API_VERSION,
)


# ---- reply-body formatting (pure function tests) ------------------------

def test_format_reply_pending_with_summary():
    body = format_reply_body(
        action="pending",
        summary="Added null guard on user.session.",
        commits=["abc1234", "def5678"],
        trivial=False,
    )
    assert body == (
        "**Addressed in abc1234, def5678**\n\n"
        "Added null guard on user.session.\n\n"
        "Marked as pending for reviewer confirmation."
    )


def test_format_reply_pending_trivial():
    body = format_reply_body(
        action="pending",
        summary=None,
        commits=["abc1234"],
        trivial=True,
    )
    assert body == "Trivial fix in abc1234, marking pending."


def test_format_reply_wontfix():
    body = format_reply_body(
        action="wontfix",
        summary="Test exists in auth.integration.test.ts:55, not the unit file.",
        commits=[],
        trivial=False,
    )
    assert body == (
        "**Not fixing in this PR**\n\n"
        "Test exists in auth.integration.test.ts:55, not the unit file.\n\n"
        "Marked won't-fix."
    )


def test_format_reply_reply_only():
    body = format_reply_body(
        action="reply-only",
        summary="Good question — see commit msg of abc1234 for rationale.",
        commits=[],
        trivial=False,
    )
    # No template footer for reply-only.
    assert body == "Good question — see commit msg of abc1234 for rationale."


# ---- HTTP shape (one test per action) -----------------------------------

ORG, PROJ, REPO, PR, THREAD = "example", "proj", "repo", 1234, 9876
THREAD_URL = (
    f"https://dev.azure.com/{ORG}/{PROJ}/_apis/git/repositories/{REPO}/"
    f"pullRequests/{PR}/threads/{THREAD}"
)
COMMENTS_URL = THREAD_URL + "/comments"


@responses.activate
def test_post_update_pending_posts_comment_and_patches_status(monkeypatch):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    responses.post(re.compile(re.escape(COMMENTS_URL) + r"\?api-version="),
                   json={"id": 99}, status=200)
    responses.patch(re.compile(re.escape(THREAD_URL) + r"\?api-version="),
                    json={"id": THREAD, "status": "pending"}, status=200)

    post_update(
        org=ORG, project=PROJ, repo=REPO, pr=PR, thread_id=THREAD,
        action="pending",
        body="Addressed in abc1234. Marked pending.",
    )

    assert len(responses.calls) == 2
    post_call = responses.calls[0]
    patch_call = responses.calls[1]
    assert post_call.request.method == "POST"
    assert json.loads(post_call.request.body)["content"] == \
        "Addressed in abc1234. Marked pending."
    assert post_call.request.url.endswith(f"api-version={AZDO_API_VERSION}")
    assert patch_call.request.method == "PATCH"
    assert json.loads(patch_call.request.body) == {"status": "pending"}


@responses.activate
def test_post_update_wontfix_patches_wontFix_status(monkeypatch):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    responses.post(re.compile(re.escape(COMMENTS_URL) + r"\?api-version="),
                   json={"id": 99}, status=200)
    responses.patch(re.compile(re.escape(THREAD_URL) + r"\?api-version="),
                    json={"id": THREAD, "status": "wontFix"}, status=200)

    post_update(
        org=ORG, project=PROJ, repo=REPO, pr=PR, thread_id=THREAD,
        action="wontfix",
        body="**Not fixing in this PR**\n\n…",
    )

    assert len(responses.calls) == 2
    assert responses.calls[1].request.method == "PATCH"
    assert json.loads(responses.calls[1].request.body) == {"status": "wontFix"}


@responses.activate
def test_post_update_reply_only_does_not_patch(monkeypatch):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    responses.post(re.compile(re.escape(COMMENTS_URL) + r"\?api-version="),
                   json={"id": 99}, status=200)

    post_update(
        org=ORG, project=PROJ, repo=REPO, pr=PR, thread_id=THREAD,
        action="reply-only",
        body="Good question — see commit msg.",
    )

    # Exactly one call, the POST. No PATCH.
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"
```

- [ ] **Step 2: Run, expect failures**

Run: `.venv/bin/pytest tests/test_update_azdo_payload.py -v`
Expected: import errors.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_update_azdo_payload.py
git commit -m "test(update): add failing tests for update_azdo HTTP shape"
```

---

### Task 8.2: Implement `update_azdo.py`

**Files:**
- Create: `skills/pr-review-update/scripts/update_azdo.py`

**Spec ref:** §6.4, §6.5 step 4, §6.6.

- [ ] **Step 1: Implement**

```python
#!/usr/bin/env python3
"""Post a reply on an AzDO PR review thread and (optionally) flip status.

Usage (CLI form, called by SKILL.md):
    update_azdo.py
      --org <org> --project <project> --repo <repo> --pr <n>
      --thread-id <int>
      --action {pending|wontfix|reply-only}
      --body <verbatim reply body>

Programmatic form: import post_update / format_reply_body.

Auth: prefers AZURE_DEVOPS_EXT_PAT (HTTP Basic). Falls back to az CLI
session if PAT is absent.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Iterable

import requests

AZDO_API_VERSION = "7.1"


# ----- error helpers -----------------------------------------------------

def _fail(code: str, message: str, fix: str | None = None) -> None:
    json.dump({"error": code, "message": message, "fix": fix}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


# ----- reply formatting (pure) -------------------------------------------

def format_reply_body(
    *, action: str, summary: str | None, commits: Iterable[str], trivial: bool,
) -> str:
    commits_str = ", ".join(commits) if commits else ""
    if action == "pending":
        if trivial:
            return f"Trivial fix in {commits_str}, marking pending."
        assert summary is not None
        return (
            f"**Addressed in {commits_str}**\n\n"
            f"{summary}\n\n"
            f"Marked as pending for reviewer confirmation."
        )
    if action == "wontfix":
        assert summary is not None
        return (
            "**Not fixing in this PR**\n\n"
            f"{summary}\n\n"
            "Marked won't-fix."
        )
    if action == "reply-only":
        assert summary is not None
        return summary
    _fail("usage", f"unknown action: {action!r}")
    raise AssertionError("unreachable")


# ----- HTTP --------------------------------------------------------------

def _thread_url(org: str, project: str, repo: str, pr: int, thread_id: int) -> str:
    return (
        f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/"
        f"{repo}/pullRequests/{pr}/threads/{thread_id}"
    )


def _auth() -> tuple[str, str] | None:
    pat = os.environ.get("AZURE_DEVOPS_EXT_PAT")
    return ("", pat) if pat else None


def _post(url: str, json_body: dict) -> requests.Response:
    auth = _auth()
    if auth is None:
        # Fallback: use az rest. For brevity, only PAT path is fully wired
        # here; az-rest path mirrors fetch_azdo._call_azdo_api and is left
        # to the reader if PAT is absent. SKILL.md instructs the user to
        # set AZURE_DEVOPS_EXT_PAT for write operations.
        if shutil.which("az") is None:
            _fail("azdo_not_logged_in",
                  "no AZURE_DEVOPS_EXT_PAT and no az CLI",
                  "Export AZURE_DEVOPS_EXT_PAT=<pat> with 'Pull Request Threads (read & write)' scope.")
        proc = subprocess.run(
            ["az", "rest", "--method", "POST", "--url", url,
             "--body", json.dumps(json_body),
             "--headers", "Content-Type=application/json"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            _fail("azdo_api_failure", f"az rest POST failed: {proc.stderr.strip()}")
        # Fake a Response so callers can use the same code path.
        r = requests.Response()
        r.status_code = 200
        r._content = proc.stdout.encode()
        return r
    return requests.post(url, json=json_body, auth=auth, timeout=30)


def _patch(url: str, json_body: dict) -> requests.Response:
    auth = _auth()
    if auth is None:
        if shutil.which("az") is None:
            _fail("azdo_not_logged_in",
                  "no AZURE_DEVOPS_EXT_PAT and no az CLI",
                  "Export AZURE_DEVOPS_EXT_PAT=<pat>.")
        proc = subprocess.run(
            ["az", "rest", "--method", "PATCH", "--url", url,
             "--body", json.dumps(json_body),
             "--headers", "Content-Type=application/json"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            _fail("azdo_api_failure", f"az rest PATCH failed: {proc.stderr.strip()}")
        r = requests.Response(); r.status_code = 200; r._content = proc.stdout.encode()
        return r
    return requests.patch(url, json=json_body, auth=auth, timeout=30)


# ----- public API --------------------------------------------------------

def post_update(
    *, org: str, project: str, repo: str, pr: int, thread_id: int,
    action: str, body: str,
) -> None:
    """Post a comment, then PATCH status if the action requires."""
    base = _thread_url(org, project, repo, pr, thread_id)
    comments_url = f"{base}/comments?api-version={AZDO_API_VERSION}"
    thread_url = f"{base}?api-version={AZDO_API_VERSION}"

    # Comment
    resp = _post(comments_url, {"content": body, "commentType": "text"})
    if resp.status_code in (401, 403):
        _fail("azdo_pat_invalid", f"AzDO returned {resp.status_code}",
              "PAT lacks 'Pull Request Threads (read & write)'.")
    if resp.status_code >= 400:
        _fail("azdo_api_failure", f"comment POST: {resp.status_code} {resp.text[:200]}")

    # Status
    if action == "pending":
        new_status = "pending"
    elif action == "wontfix":
        new_status = "wontFix"
    elif action == "reply-only":
        return
    else:
        _fail("usage", f"unknown action: {action!r}")
        return

    resp = _patch(thread_url, {"status": new_status})
    if resp.status_code >= 400:
        _fail("azdo_api_failure", f"status PATCH: {resp.status_code} {resp.text[:200]}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--org", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--thread-id", required=True, type=int)
    p.add_argument("--action", required=True, choices=["pending", "wontfix", "reply-only"])
    p.add_argument("--body", required=True)
    args = p.parse_args(argv[1:])
    post_update(
        org=args.org, project=args.project, repo=args.repo, pr=args.pr,
        thread_id=args.thread_id, action=args.action, body=args.body,
    )
    print(json.dumps({"ok": True, "thread_id": args.thread_id, "action": args.action}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Make executable**

Run: `chmod +x skills/pr-review-update/scripts/update_azdo.py`

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_update_azdo_payload.py -v`
Expected: 7 PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/pr-review-update/scripts/update_azdo.py
git commit -m "feat(update): implement AzDO updater"
```

---

### Task 8.3: Author `references/reply-templates.md`

**Files:**
- Create: `skills/pr-review-update/references/reply-templates.md`

**Spec ref:** §6.6.

- [ ] **Step 1: Write reference**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-update/references/reply-templates.md
git commit -m "docs(update): add reply-templates reference"
```

---

### Task 8.4: Author `pr-review-update/SKILL.md`

**Files:**
- Create: `skills/pr-review-update/SKILL.md`

**Spec ref:** §6 in full.

- [ ] **Step 1: Write `SKILL.md`**

````markdown
---
name: pr-review-update
description: Use when the user explicitly invokes /pr-review-update or names a specific PR review thread to update (e.g. "mark thread azdo:9876 as pending", "post my fix for thread X", "mark thread Y won't-fix"). Do NOT trigger automatically after implementing a fix — wait for an explicit ask. Azure DevOps in v1; GitHub write-side deferred.
---

# pr-review-update

Post a single reply to a PR review thread, optionally flipping its
status. Verifies real git evidence before posting `--action pending`.

## When to use

- User typed `/pr-review-update --thread <id> ...`.
- User explicitly asked you to mark a specific thread as pending,
  won't-fix, or to post a reply.

**Do NOT auto-trigger** when you finish implementing a fix. Wait for an
explicit ask. The hard rule: a fix being implemented in code does NOT
imply the user wants the thread updated — they may have a batch
workflow, may want to inspect first, or may want to update via a
different channel.

## Invocation

```
/pr-review-update
  --thread <id>                              (required, e.g. azdo:9876)
  [--action pending|wontfix|reply-only]      (default: pending)
  [--commits <sha,sha,...>]                  (default: HEAD; ignored for reply-only)
  (--summary '...' | --trivial)              (one is required, except reply-only must use --summary)
  [--force-line-unchanged]                   (override the line-range warn for --action pending)
```

`--trivial` is only valid with `--action pending`.

## Steps

1. **Resolve the thread.** Read `./docs/pr/<pr>-active.json` (created by
   `pr-review-intake`) to find the entry matching `--thread`. If the
   file is missing or the thread isn't in it, ask the user to re-run
   `pr-review-intake` first and stop.

2. **Sanity-check the thread's current status** by re-fetching it from
   the provider (run the relevant `fetch_*` script and look for the
   thread). If the current normalized status is `pending` or
   `resolved`, print "thread <id> is already <status>, skipping." and
   exit 0. (This makes batch retries safe.)

3. **Verify git evidence** (only if `--action pending`). Run:
   ```bash
   python3 ../pr-review-update/scripts/verify_git_evidence.py \
     --file <thread.file> \
     --original-line <thread.original_line> \
     --first-comment-iso <thread.first_comment.created_at> \
     --commits <commits>
   ```
   - Exit 0 → pass.
   - Exit 2 (`git_evidence_line_unchanged`) → tell the user; if they
     pass `--force-line-unchanged`, proceed.
   - Exit 1 (`git_evidence_file_unchanged`) → HARD BLOCK. Surface the
     stderr `fix` field and stop. Suggest `--action wontfix` or
     `--action reply-only`.

   Skip this step entirely for `wontfix` and `reply-only`.

4. **Post + transition.** For Azure DevOps:
   ```bash
   python3 scripts/update_azdo.py \
     --org <...> --project <...> --repo <...> --pr <pr> \
     --thread-id <numeric id from after the colon in the thread id> \
     --action <action> \
     --body "$(...formatted body...)"
   ```
   The body is generated by `update_azdo.format_reply_body(...)` (see
   `references/reply-templates.md`).

   For GitHub: not implemented in v1. Fail with
   `github_write_unsupported_v1` and direct the user to AzDO or wait
   for v1.1.

5. **Report.** Print one of:
   - "Thread <id> marked <new_status>. View: <url>"
   - "Reply posted on thread <id>. View: <url>"

## Constraints (hard rules)

- ONE thread per invocation. No batch mode in v1.
- `--action pending` is hard-gated on `git_evidence_file_unchanged`.
- Never marks a thread `resolved` (`fixed`/`closed`/`byDesign`).
  Reviewer territory. `wontFix` is allowed because it's the PR
  author's call.
- Never posts general PR-level comments. Only existing threads.
- Reply text format is fixed. Agent's only input is `--summary`.
- On API failure: surface the error verbatim, exit non-zero, no retry.

## Working-tree expectations

The verifier inspects committed history. Commit your fix BEFORE
invoking this skill. A dirty working tree triggers a `working_tree_dirty`
diagnostic but does not block.

## References

- `references/verification-rules.md` — what file/line checks mean and
  how to override.
- `references/reply-templates.md` — pinned reply text formats.
- The intake skill's `references/auth.md` and `references/errors.md`
  also apply here.
````

- [ ] **Step 2: Commit**

```bash
git add skills/pr-review-update/SKILL.md
git commit -m "feat(update): add SKILL.md entry point"
```

---

## Phase 9 — manual smoke test guide + README + release prep

### Task 9.1: Write `tests/README.md`

**Files:**
- Create: `tests/README.md`

**Spec ref:** §10.

- [ ] **Step 1: Write the README**

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add tests/README.md
git commit -m "docs(test): add tests README and smoke-test recipe"
```

---

### Task 9.2: Expand the top-level README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read existing README**

Run: `cat README.md`
Expected: the current 2-line README.

- [ ] **Step 2: Replace with the v1 README**

Use Write to replace the file with:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: expand README for v1"
```

---

### Task 9.3: Update `CHANGELOG.md` for the v0.1.0 release

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Read existing CHANGELOG**

Run: `cat CHANGELOG.md`

- [ ] **Step 2: Update**

Replace the file with:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for v0.1.0"
```

---

### Task 9.4: Run the full test suite end-to-end

**Files:** none modified.

- [ ] **Step 1: Run all tests with verbose output**

Run: `.venv/bin/pytest -v`
Expected: every test passes. Total ≈ 50 tests.

- [ ] **Step 2: Verify the manifest is valid JSON**

Run: `python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['name'])"`
Expected: `teampowers`.

- [ ] **Step 3: Check tree shape matches the spec layout**

Run:
```bash
find . -path ./.git -prune -o -path ./.venv -prune -o -path ./docs/research -prune -o -type f -print \
  | sort
```
Expected (modulo `__pycache__`): every file in §3.1 of the spec exists.

- [ ] **Step 4: Tag the release commit**

```bash
git tag -a v0.1.0 -m "teampowers v0.1.0 — pr-review-intake + pr-review-update"
```

(If you don't tag, that's fine — the README's "v1 ships" is the marker.)

---

### Task 9.5: Clean up the transient `docs/research/` directory

**Files:**
- Delete: `docs/research/` (entire directory)

The user noted this was a temporary holding area, to be deleted once the spec and plan are reviewed. By the time we reach this task, both are in place.

- [ ] **Step 1: Confirm with the user before deleting**

Print to the conversation: "About to delete `docs/research/` (the transient brainstorming notes). Spec is at `docs/specs/...` and plan is at `docs/plans/...`. OK to proceed?"

Wait for explicit confirmation.

- [ ] **Step 2: After confirmation, delete and commit**

```bash
rm -rf docs/research
git add -A docs/
git commit -m "chore: remove transient research notes"
```

(If the directory was never tracked, `git status` will simply show no changes — in that case, just `rm -rf docs/research` and skip the commit.)

---

## Self-review (after writing the plan, before handoff)

This section is the writing-plans skill's required self-check, captured here so reviewers can see what was checked.

### Spec coverage

| Spec section | Covered by | Notes |
|---|---|---|
| §1.1 plugin identity | Task 1.2 (manifest), Task 9.2 (README) | ✓ |
| §1.2 separate plugin rationale | Task 9.2 (README) | Mentioned in README. |
| §1.3 v1 scope | Phases 3–8 | Both skills, AzDO full, GitHub read-only. |
| §1.4 out-of-scope | Tasks 8.4 (SKILL.md), 9.3 (changelog) | Explicit non-goals listed. |
| §1.5 future skills | 9.2 (README roadmap) | ✓ |
| §2 architectural principles | Encoded in test expectations + SKILL.md text | No code-inspection in scripts; no caching; no LLM in scripts. |
| §3 repo structure | Phases 1, 6, 8 | Every file in the layout has a creation task. |
| §4 normalized schema | Task 2.1, 2.2, 2.3, 2.4 | Schema, sample, tests, reference all present. |
| §5 pr-review-intake | Phases 3–6 | Filter, render, fetchers, detect, SKILL.md. |
| §6 pr-review-update | Phases 7–8 | Verify, update, SKILL.md. |
| §7 authentication | Tasks 5.7, 6.3, 8.2 | az/PAT for AzDO, gh/GH_TOKEN for GitHub. |
| §8 error contract | Task 6.4 + every script's `_fail()` | Error codes enumerated in errors.md. |
| §9 adding providers | Task 6.5 | Reference doc included. |
| §10 testing strategy | Phases 3.1, 4.1, 5.1, 5.3, 5.6, 5.9, 6.1, 7.1, 8.1 + Task 9.1 | Every component listed in §10.1 has a test task. Manual smoke is in 9.1. |
| §11 risks | Mitigated by SKILL.md trigger discipline + verifier hard-block + API-version pin | ✓ |
| §12 e2e example | Task 6.7 (intake fixture) + 9.1 (manual smoke recipe) | Validated against the spec example shape. |

### Placeholder scan

Searched for: TBD, TODO, "implement later", "fill in details", "appropriate error handling", "similar to Task N", incomplete code blocks. None found. Two acceptable forward-references:

- The az-rest fallback path in `update_azdo.py` (PATCH/POST helpers) is implemented but lightly tested. It's not strictly *required* for v1 — the spec allows PAT to be the primary write-path. Documented in `update_azdo.py` docstring; manual smoke test exercises whichever path the user has configured.
- Task 9.5 asks for user confirmation before deleting `docs/research/`. This is a "stop and ask" step, not a placeholder — destructive operation requires explicit go-ahead per harness guidance.

### Type/name consistency check

- `_status_map.normalize_azdo` / `normalize_github` — used identically in fetchers and tests. ✓
- `_anchor.is_anchor_lost(repo_root, file, original_line)` — same signature in `_anchor.py`, `fetch_azdo.py`, `fetch_github.py`, and tests. ✓
- `verify_git_evidence.verify(...)` — keyword args match between implementation, tests, and CLI parser. ✓
- `update_azdo.format_reply_body(*, action, summary, commits, trivial)` and `post_update(*, org, project, repo, pr, thread_id, action, body)` — keyword-only signatures match between implementation and tests. ✓
- Filter envelope `{"active": [...], "counts": {...}}` — produced by `filter_active`, consumed by `render_report` (under that exact key set, plus `"context"`). ✓
- Error code strings (`git_evidence_file_unchanged`, etc.) — same spelling in `errors.md`, `verify_git_evidence.py`, and the corresponding tests. ✓

---
