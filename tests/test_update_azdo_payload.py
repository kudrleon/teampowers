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


# ---- CLI behavior ------------------------------------------------------

import json
from pathlib import Path
from unittest.mock import patch

from update_azdo import main as cli_main


def _persisted_active(thread_id: str = "azdo:9876") -> dict:
    return {
        "active": [
            {
                "id": thread_id,
                "provider": "azdo",
                "url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234?discussionId=9876",
                "status": "active",
                "file": "src/auth.ts",
                "line": 42,
                "original_line": 40,
                "anchor_lost": False,
                "first_comment": {
                    "author": "alice",
                    "created_at": "2026-04-22T14:30:00Z",
                    "body": "null check?",
                },
                "replies": [],
                "is_bot": False,
                "is_outdated": False,
                "raw_status": "active",
            }
        ],
        "counts": {"total": 1, "active": 1, "pending": 0, "resolved": 0},
        "context": {
            "provider": "azdo",
            "provider_display": "Azure DevOps",
            "branch": "feature/auth-refactor",
            "pr_number": 1234,
            "pr_url": "https://dev.azure.com/example/proj/_git/repo/pullrequest/1234",
            "org": "example",
            "project": "proj",
            "repo": "repo",
        },
    }


def test_cli_reads_context_and_resolves_thread(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    monkeypatch.chdir(tmp_path)
    pr_dir = tmp_path / "docs" / "pr"
    pr_dir.mkdir(parents=True)
    (pr_dir / "1234-active.json").write_text(json.dumps(_persisted_active()))

    captured = {}

    def fake_post_update(*, org, project, repo, pr, thread_id, action, body):
        captured.update(
            org=org, project=project, repo=repo, pr=pr,
            thread_id=thread_id, action=action, body=body,
        )

    with patch("update_azdo.post_update", side_effect=fake_post_update):
        rc = cli_main([
            "update_azdo.py",
            "--thread", "azdo:9876",
            "--action", "pending",
            "--commits", "abc1234",
            "--summary", "Added null guard.",
        ])
    assert rc == 0
    # Coordinates came from the persisted context block, not from CLI flags.
    assert captured["org"] == "example"
    assert captured["project"] == "proj"
    assert captured["repo"] == "repo"
    assert captured["pr"] == 1234
    assert captured["thread_id"] == 9876
    assert captured["action"] == "pending"
    assert "Addressed in abc1234" in captured["body"]
    assert "Added null guard." in captured["body"]


def test_cli_fails_clearly_when_thread_missing_from_active_json(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    monkeypatch.chdir(tmp_path)
    pr_dir = tmp_path / "docs" / "pr"
    pr_dir.mkdir(parents=True)
    (pr_dir / "1234-active.json").write_text(json.dumps(_persisted_active()))

    with patch("update_azdo.post_update"):
        with pytest.raises(SystemExit) as exc:
            cli_main([
                "update_azdo.py",
                "--thread", "azdo:9999",  # not in fixture
                "--summary", "x",
            ])
    assert exc.value.code == 1


def test_cli_fails_clearly_when_pat_missing(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.delenv("AZURE_DEVOPS_EXT_PAT", raising=False)
    monkeypatch.chdir(tmp_path)
    pr_dir = tmp_path / "docs" / "pr"
    pr_dir.mkdir(parents=True)
    (pr_dir / "1234-active.json").write_text(json.dumps(_persisted_active()))

    # Patch requests so a real network call can't happen if PAT-check fails to fire.
    with patch("update_azdo.requests.post") as mock_post:
        with pytest.raises(SystemExit) as exc:
            cli_main([
                "update_azdo.py",
                "--thread", "azdo:9876",
                "--commits", "abc1234",
                "--summary", "x",
            ])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "azdo_not_logged_in" in err
    mock_post.assert_not_called()


def test_cli_fails_clearly_when_no_active_json(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    monkeypatch.chdir(tmp_path)  # no docs/pr/ at all

    with pytest.raises(SystemExit) as exc:
        cli_main([
            "update_azdo.py",
            "--thread", "azdo:9876",
            "--commits", "abc1234",
            "--summary", "x",
        ])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "thread_not_found" in err
    assert "Re-run /pr-review-intake" in err


def test_cli_rejects_trivial_with_non_pending_action(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    monkeypatch.chdir(tmp_path)
    pr_dir = tmp_path / "docs" / "pr"
    pr_dir.mkdir(parents=True)
    (pr_dir / "1234-active.json").write_text(json.dumps(_persisted_active()))

    with pytest.raises(SystemExit) as exc:
        cli_main([
            "update_azdo.py",
            "--thread", "azdo:9876",
            "--action", "wontfix",
            "--trivial",
        ])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "trivial" in err.lower()


def test_cli_namespaced_id_is_required(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "fake-pat")
    monkeypatch.chdir(tmp_path)
    pr_dir = tmp_path / "docs" / "pr"
    pr_dir.mkdir(parents=True)
    (pr_dir / "1234-active.json").write_text(json.dumps(_persisted_active()))

    with pytest.raises(SystemExit) as exc:
        cli_main([
            "update_azdo.py",
            "--thread", "9876",  # missing 'azdo:' prefix
            "--summary", "x",
        ])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "namespaced" in err
