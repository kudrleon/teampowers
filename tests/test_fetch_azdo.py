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


def test_fetch_azdo_skips_deleted_and_empty_comment_threads(fake_workspace, monkeypatch):
    """Deleted threads and threads with no comments are silently dropped."""
    monkeypatch.chdir(fake_workspace)
    from fetch_azdo import fetch
    raw = {
        "value": [
            # Deleted thread — should be dropped.
            {
                "id": 1001,
                "isDeleted": True,
                "status": "active",
                "threadContext": {
                    "filePath": "/src/auth.ts",
                    "rightFileStart": {"line": 10, "offset": 1},
                },
                "pullRequestThreadContext": {"trackingCriteria": {"origLine": 10}},
                "comments": [
                    {"id": 1, "parentCommentId": 0,
                     "author": {"displayName": "alice", "uniqueName": "alice@example.com"},
                     "publishedDate": "2026-04-22T14:30:00Z",
                     "content": "deleted comment",
                     "commentType": "text"},
                ],
                "_links": {"self": {"href": "https://x"}},
            },
            # Thread with no comments — should be dropped.
            {
                "id": 1002,
                "isDeleted": False,
                "status": "active",
                "threadContext": {
                    "filePath": "/src/auth.ts",
                    "rightFileStart": {"line": 20, "offset": 1},
                },
                "pullRequestThreadContext": {"trackingCriteria": {"origLine": 20}},
                "comments": [],
                "_links": {"self": {"href": "https://x"}},
            },
            # Normal thread — should be kept.
            {
                "id": 1003,
                "isDeleted": False,
                "status": "active",
                "publishedDate": "2026-04-22T14:30:00Z",
                "threadContext": {
                    "filePath": "/src/auth.ts",
                    "rightFileStart": {"line": 30, "offset": 1},
                },
                "pullRequestThreadContext": {"trackingCriteria": {"origLine": 30}},
                "comments": [
                    {"id": 1, "parentCommentId": 0,
                     "author": {"displayName": "alice", "uniqueName": "alice@example.com"},
                     "publishedDate": "2026-04-22T14:30:00Z",
                     "content": "kept comment",
                     "commentType": "text"},
                ],
                "_links": {"self": {"href": "https://x"}},
            },
        ],
    }
    with patch("fetch_azdo._call_azdo_api", return_value=raw):
        threads = fetch(org="example", project="proj", repo="repo", pr=1234)
    ids = [t["id"] for t in threads]
    assert ids == ["azdo:1003"]  # only the normal thread survives
