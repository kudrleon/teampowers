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
