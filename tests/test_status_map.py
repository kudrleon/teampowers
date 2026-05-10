"""Tests for _status_map: provider raw status -> normalized status."""
import pytest

from _status_map import normalize_azdo, normalize_github


@pytest.mark.parametrize("raw,expected", [
    ("active",   "active"),
    ("pending",  "pending"),
    ("fixed",    "resolved"),
    ("closed",   "resolved"),
    ("byDesign", "resolved"),
    ("wontFix",  "resolved"),
    ("unknown",  "active"),  # spec: treat conservatively
])
def test_normalize_azdo(raw, expected):
    assert normalize_azdo(raw) == expected


@pytest.mark.parametrize("is_resolved,expected", [
    (True,  "resolved"),
    (False, "active"),
])
def test_normalize_github(is_resolved, expected):
    assert normalize_github(is_resolved) == expected


def test_normalize_azdo_unknown_value_defaults_to_active():
    # Future-proofing: any unrecognized value is treated as 'active'.
    assert normalize_azdo("some-future-status") == "active"
