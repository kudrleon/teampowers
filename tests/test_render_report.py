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
