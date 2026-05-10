"""Tests for scripts/detect_context.sh.

Builds throwaway git repos in tmp_path with various remote URLs, runs
the script via subprocess, and asserts on the JSON it emits.

We do NOT exercise the PR-lookup path here (that requires `az` / `gh` and
network). We mock those by setting environment variables the script
checks.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/pr-review-intake/scripts/detect_context.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _init_repo(tmp_path: Path, remote_url: str, branch: str = "feature/x") -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "--initial-branch", branch)
    _git(repo, "remote", "add", "origin", remote_url)
    # Need at least one commit so HEAD exists
    (repo / "f").write_text("hello\n")
    _git(repo, "add", "f")
    _git(repo, "-c", "user.email=test@x", "-c", "user.name=test", "commit", "-m", "init")
    return repo


def _run(repo: Path, env_extra: dict | None = None) -> dict:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "TEAMPOWERS_TEST": "1"}
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(repo), env=env,
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # Caller can still parse stderr JSON when expecting failure.
        return {"_exit": proc.returncode, "_stderr": proc.stderr, "_stdout": proc.stdout}
    return json.loads(proc.stdout)


def test_detects_azdo_remote(tmp_path):
    repo = _init_repo(tmp_path, "https://dev.azure.com/example/proj/_git/repo")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "1234"})
    assert out["provider"] == "azdo"
    assert out["org"] == "example"
    assert out["project"] == "proj"
    assert out["repo"] == "repo"
    assert out["branch"] == "feature/x"
    assert out["pr_number"] == "1234"


def test_detects_azdo_ssh_remote(tmp_path):
    repo = _init_repo(tmp_path, "git@ssh.dev.azure.com:v3/example/proj/repo")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "1234"})
    assert out["provider"] == "azdo"
    assert out["org"] == "example"
    assert out["project"] == "proj"
    assert out["repo"] == "repo"


def test_detects_github_https(tmp_path):
    repo = _init_repo(tmp_path, "https://github.com/example/repo.git")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "777"})
    assert out["provider"] == "github"
    assert out["repo"] == "example/repo"
    assert out["pr_number"] == "777"


def test_detects_github_ssh(tmp_path):
    repo = _init_repo(tmp_path, "git@github.com:example/repo.git")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": "777"})
    assert out["provider"] == "github"
    assert out["repo"] == "example/repo"


def test_unsupported_remote(tmp_path):
    repo = _init_repo(tmp_path, "https://gitlab.com/example/repo.git")
    out = _run(repo)
    assert out.get("_exit", 0) != 0
    err = json.loads(out["_stderr"])
    assert err["error"] == "unsupported_provider"


def test_no_pr_for_branch(tmp_path):
    repo = _init_repo(tmp_path, "https://github.com/example/repo.git")
    out = _run(repo, env_extra={"TEAMPOWERS_FAKE_PR": ""})
    assert out.get("_exit", 0) != 0
    err = json.loads(out["_stderr"])
    assert err["error"] == "no_pr_for_branch"
