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
