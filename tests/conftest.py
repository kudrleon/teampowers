"""Pytest config — adjust import path for skill scripts."""
# pyproject.toml's `pythonpath` already covers this, but conftest.py
# guarantees the same paths for ad-hoc invocations.
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
for sub in (
    "skills/pr-review-intake/scripts",
    "skills/pr-review-update/scripts",
):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
