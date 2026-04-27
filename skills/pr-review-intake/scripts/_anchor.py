"""Compute anchor_lost for a thread.

Pure helper — single existence check + line count. The only "code
inspection" the intake skill is allowed to do (spec §5.5).
"""
from pathlib import Path


def is_anchor_lost(repo_root: Path, file: str, original_line: int) -> bool:
    """Return True if `file` no longer exists OR `original_line` is past EOF.

    `repo_root` is the working-tree root the script is invoked from.
    """
    p = repo_root / file
    if not p.is_file():
        return True
    # Count lines. Iterating a binary file yields each line including the
    # trailing newline; a final fragment without a newline is still yielded
    # as the last line, so this counts both forms correctly.
    with p.open("rb") as f:
        lines = sum(1 for _ in f)
    return original_line > lines
