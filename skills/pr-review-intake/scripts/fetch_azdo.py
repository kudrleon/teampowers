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


def _normalize_thread(org: str, project: str, repo: str, pr: int, t: dict, repo_root: Path) -> dict | None:
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
        return None

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
