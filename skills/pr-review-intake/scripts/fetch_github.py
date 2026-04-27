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
