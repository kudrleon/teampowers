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
