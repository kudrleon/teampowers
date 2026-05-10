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
