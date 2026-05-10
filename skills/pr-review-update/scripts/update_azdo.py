#!/usr/bin/env python3
"""Post a reply on an AzDO PR review thread and (optionally) flip status.

Usage (CLI form, called by SKILL.md):
    update_azdo.py
      --thread <namespaced-id, e.g. azdo:9876>
      [--action pending|wontfix|reply-only]   default: pending
      [--commits <sha,sha,...>]               default: HEAD; ignored for reply-only
      (--summary '...' | --trivial)           one is required, except reply-only
                                              (which must use --summary; --trivial is
                                              only valid with --action pending)
      [--active-json <path>]                  default: ./docs/pr/<pr>-active.json
                                              auto-discovered from the active.json
                                              files in ./docs/pr/

The script reads the persisted handoff (./docs/pr/<n>-active.json,
written by pr-review-intake) to get the thread metadata AND the AzDO
PR coordinates from the `context` block. It does NOT re-detect.

Programmatic form: import post_update / format_reply_body.

Auth: AZURE_DEVOPS_EXT_PAT (HTTP Basic) is REQUIRED for write
operations. v1 does not auto-fall-back to `az rest` for writes — the
fallback was dropped because parsing `az rest` HTTP status codes
out of its returncode/stdout is unreliable, and silent success is
worse than a clear "set the PAT" error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
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
        if summary is None:
            _fail("usage", "--summary is required for --action pending (unless --trivial)")
        return (
            f"**Addressed in {commits_str}**\n\n"
            f"{summary}\n\n"
            f"Marked as pending for reviewer confirmation."
        )
    if action == "wontfix":
        if summary is None:
            _fail("usage", "--summary is required for --action wontfix")
        return (
            "**Not fixing in this PR**\n\n"
            f"{summary}\n\n"
            "Marked won't-fix."
        )
    if action == "reply-only":
        if summary is None:
            _fail("usage", "--summary is required for --action reply-only")
        return summary
    _fail("usage", f"unknown action: {action!r}")
    raise AssertionError("unreachable")  # _fail exits


# ----- HTTP --------------------------------------------------------------

def _thread_url(org: str, project: str, repo: str, pr: int, thread_id: int) -> str:
    return (
        f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/"
        f"{repo}/pullRequests/{pr}/threads/{thread_id}"
    )


def _auth() -> tuple[str, str]:
    pat = os.environ.get("AZURE_DEVOPS_EXT_PAT")
    if not pat:
        _fail(
            "azdo_not_logged_in",
            "AZURE_DEVOPS_EXT_PAT is not set",
            "Export AZURE_DEVOPS_EXT_PAT=<pat> with 'Pull Request Threads (read & write)' scope.",
        )
    return ("", pat)  # type: ignore[unreachable]


def _post(url: str, json_body: dict) -> requests.Response:
    return requests.post(url, json=json_body, auth=_auth(), timeout=30)


def _patch(url: str, json_body: dict) -> requests.Response:
    return requests.patch(url, json=json_body, auth=_auth(), timeout=30)


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


# ----- CLI helpers -------------------------------------------------------

def _parse_thread_id(namespaced: str) -> tuple[str, int]:
    """`azdo:9876` -> ("azdo", 9876). Fails otherwise."""
    if ":" not in namespaced:
        _fail("usage", f"--thread must be namespaced (e.g. azdo:9876), got {namespaced!r}")
    provider, _, raw = namespaced.partition(":")
    try:
        return provider, int(raw)
    except ValueError:
        _fail("usage", f"--thread numeric part must be an integer, got {raw!r}")
        raise AssertionError("unreachable")  # _fail exits


def _find_active_json(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            _fail("thread_not_found", f"no such file: {explicit}",
                  "Re-run /pr-review-intake first.")
        return p
    pr_dir = Path("./docs/pr")
    if not pr_dir.is_dir():
        _fail("thread_not_found", "no ./docs/pr/ directory",
              "Re-run /pr-review-intake first.")
    candidates = sorted(pr_dir.glob("*-active.json"))
    if not candidates:
        _fail("thread_not_found", "no ./docs/pr/*-active.json files",
              "Re-run /pr-review-intake first.")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        _fail("thread_not_found",
              f"multiple ./docs/pr/*-active.json found: {names}",
              "Pass --active-json <path> to disambiguate.")
    return candidates[0]


def _resolve_thread(persisted: dict, thread_id: str) -> dict:
    """Find the thread by namespaced id in the persisted active list."""
    for t in persisted.get("active", []):
        if t.get("id") == thread_id:
            return t
    _fail("thread_not_found",
          f"thread {thread_id} not in active list — already pending/resolved, "
          "or persisted file is stale",
          "Re-run /pr-review-intake first.")
    raise AssertionError("unreachable")


def _require_azdo_context(persisted: dict) -> dict:
    ctx = persisted.get("context") or {}
    if ctx.get("provider") != "azdo":
        _fail("github_write_unsupported_v1",
              f"this script only supports Azure DevOps (provider={ctx.get('provider')!r})",
              "Use a v1.1+ build for GitHub write-side, or use --action manually on AzDO.")
    for k in ("org", "project", "repo", "pr_number"):
        if not ctx.get(k):
            _fail("thread_not_found",
                  f"context.{k} missing in persisted active.json",
                  "Re-run /pr-review-intake (this build expects the merged context block — see spec §5.3 step 4).")
    return ctx


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--thread", required=True,
                   help="Namespaced thread id, e.g. azdo:9876")
    p.add_argument("--action", default="pending",
                   choices=["pending", "wontfix", "reply-only"])
    p.add_argument("--commits", default="HEAD",
                   help="Comma-separated commit SHAs (ignored for reply-only)")
    p.add_argument("--summary", default=None)
    p.add_argument("--trivial", action="store_true",
                   help="Only valid with --action pending")
    p.add_argument("--active-json", default=None,
                   help="Path to the persisted active.json (auto-discovered if not set)")
    args = p.parse_args(argv[1:])

    if args.trivial and args.action != "pending":
        _fail("usage", "--trivial is only valid with --action pending")
    if not args.trivial and args.summary is None:
        _fail("usage", "either --summary or --trivial is required")

    provider, thread_int = _parse_thread_id(args.thread)
    if provider != "azdo":
        _fail("github_write_unsupported_v1",
              f"thread provider {provider!r} not supported for write in v1",
              "Use AzDO, or wait for v1.1.")

    persisted = json.loads(_find_active_json(args.active_json).read_text())
    _resolve_thread(persisted, args.thread)  # not used directly, just validates presence
    ctx = _require_azdo_context(persisted)

    commits = [c.strip() for c in args.commits.split(",") if c.strip()]
    body = format_reply_body(
        action=args.action,
        summary=args.summary,
        commits=commits if args.action != "reply-only" else [],
        trivial=args.trivial,
    )

    post_update(
        org=ctx["org"],
        project=ctx["project"],
        repo=ctx["repo"],
        pr=int(ctx["pr_number"]),
        thread_id=thread_int,
        action=args.action,
        body=body,
    )
    print(json.dumps({"ok": True, "thread": args.thread, "action": args.action}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
