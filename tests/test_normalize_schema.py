"""Validate the canonical sample fixture against the normalized JSON Schema."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_canonical_sample_validates():
    schema = _load("normalized_schema.json")
    sample = _load("threads_normalized_sample.json")
    # Note: format checks (uri, date-time) are advisory by default. We intentionally
    # do not pass format_checker=Draft202012Validator.FORMAT_CHECKER here to avoid
    # false positives on real-world AzDO discussion URLs with query strings.
    Draft202012Validator(schema).validate(sample)


def test_schema_rejects_extra_fields():
    schema = _load("normalized_schema.json")
    sample = _load("threads_normalized_sample.json")
    bad = [dict(sample[0])]
    bad[0]["unexpected_field"] = "nope"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_schema_rejects_wrong_provider():
    schema = _load("normalized_schema.json")
    sample = _load("threads_normalized_sample.json")
    bad = [dict(sample[0])]
    bad[0]["provider"] = "weird-vcs"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)
