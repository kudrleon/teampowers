"""Tests for fetch_github: GraphQL response -> normalized JSON."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/github_threads_sample.json"
SCHEMA = ROOT / "tests/fixtures/normalized_schema.json"


def _schema():
    return Draft202012Validator(json.loads(SCHEMA.read_text()))


@pytest.fixture()
def fake_workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.ts").write_text("\n" * 60)
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "src" / "utils" / "parse.ts").write_text("\n" * 100)
    # login.ts missing → anchor lost
    return tmp_path


def test_fetch_github_normalizes_against_schema(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    _schema().validate(threads)


def test_fetch_github_status_mapping(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA1"]["status"] == "active"
    assert by_id["github:PRT_kwDOA4"]["status"] == "resolved"
    # GitHub never produces 'pending'
    assert all(t["status"] != "pending" for t in threads)


def test_fetch_github_propagates_is_outdated(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA2"]["is_outdated"] is True
    assert by_id["github:PRT_kwDOA1"]["is_outdated"] is False


def test_fetch_github_anchor_lost_for_missing_file(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA2"]["anchor_lost"] is True


def test_fetch_github_bot_detection(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    by_id = {t["id"]: t for t in threads}
    assert by_id["github:PRT_kwDOA3"]["is_bot"] is True
    assert by_id["github:PRT_kwDOA1"]["is_bot"] is False


def test_fetch_github_id_namespacing(fake_workspace, monkeypatch):
    monkeypatch.chdir(fake_workspace)
    from fetch_github import fetch
    raw = json.loads(FIXTURE.read_text())
    with patch("fetch_github._call_github_graphql", return_value=raw):
        threads = fetch(owner_repo="example/repo", pr=1234)
    assert all(t["id"].startswith("github:") for t in threads)
