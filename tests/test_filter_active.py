"""Tests for the filter_active script."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/pr-review-intake/scripts/filter_active.py"
SAMPLE = ROOT / "tests/fixtures/threads_normalized_sample.json"


def run_filter(stdin_text: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_filter_drops_pending_and_resolved():
    out = run_filter(SAMPLE.read_text())
    assert {"active", "counts"} == set(out.keys())
    statuses = [t["status"] for t in out["active"]]
    assert all(s == "active" for s in statuses)
    assert len(out["active"]) == 3


def test_filter_counts_are_correct():
    out = run_filter(SAMPLE.read_text())
    assert out["counts"] == {
        "total": 5,
        "active": 3,
        "pending": 1,
        "resolved": 1,
    }


def test_filter_preserves_order_and_full_thread_objects():
    out = run_filter(SAMPLE.read_text())
    ids = [t["id"] for t in out["active"]]
    assert ids == ["azdo:9876", "azdo:9881", "azdo:9890"]
    assert out["active"][0]["first_comment"]["author"] == "alice"
    assert out["active"][0]["replies"][0]["author"] == "leo"


def test_filter_handles_empty_input():
    out = run_filter("[]")
    assert out == {"active": [], "counts": {"total": 0, "active": 0, "pending": 0, "resolved": 0}}
