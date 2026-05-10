"""Tests for _anchor.is_anchor_lost."""
from pathlib import Path

import pytest

from _anchor import is_anchor_lost


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "exists.ts").write_text("a\nb\nc\nd\ne\n")  # 5 lines
    return tmp_path


def test_anchor_lost_when_file_missing(tmp_repo):
    assert is_anchor_lost(tmp_repo, "src/missing.ts", original_line=1) is True


def test_anchor_lost_when_line_past_eof(tmp_repo):
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=99) is True


def test_anchor_present_when_line_within_file(tmp_repo):
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=3) is False


def test_anchor_present_when_line_is_exact_eof(tmp_repo):
    # 5-line file; line 5 is valid, line 6 is past EOF.
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=5) is False
    assert is_anchor_lost(tmp_repo, "src/exists.ts", original_line=6) is True


def test_anchor_present_when_line_is_zero():
    # Some providers use 0 to mean "file-level"; spec says PR-level
    # comments are excluded by fetchers, but defensively: line 0 in any
    # existing file is treated as present.
    pass  # behavior unspecified — see spec §4.5; not tested here.


def test_file_without_trailing_newline_counts_correctly(tmp_path: Path):
    # `"a\nb\nc"` (no trailing newline) is a 3-line file. The iterator
    # over a binary file handle yields the final newline-less fragment,
    # so sum() counts it correctly; line 3 is present, line 4 is not.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "no_trailing.ts").write_text("a\nb\nc")  # 3 lines, no \n
    assert is_anchor_lost(tmp_path, "src/no_trailing.ts", original_line=3) is False
    assert is_anchor_lost(tmp_path, "src/no_trailing.ts", original_line=4) is True
