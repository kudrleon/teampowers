#!/usr/bin/env python3
"""Render the markdown report for pr-review-intake.

stdin: JSON object {
  "active":   [<thread>, ...],
  "counts":   {"total": N, "active": A, "pending": P, "resolved": R},
  "context":  {
    "provider": "azdo|github",
    "provider_display": "Azure DevOps" | "GitHub",
    "branch": str,
    "pr_number": int,
    "pr_url": str
  }
}
stdout: markdown report (see references/normalized-schema.md and the spec §5.4).
"""
import json
import sys

NEXT_STEPS = """\
**Next step:** Pick one:

- `/receiving-code-review` — evaluate each thread, decide which to fix, push
  back where appropriate, implement.
- `/brainstorming` — explore design questions raised by these comments before
  deciding on changes.
- Or pick a specific thread to focus on first.
"""

ANCHOR_LOST_BULLET = (
    "- File no longer exists in the working tree, or the original line is "
    "past the file's end."
)


def render_thread(index: int, t: dict) -> list[str]:
    lines: list[str] = []
    heading = f"### Thread {index} — `{t['file']}:{t['line']}`"
    if t["anchor_lost"]:
        heading += " ⚠️ anchor lost"
    lines.append(heading)
    if t["anchor_lost"]:
        lines.append(ANCHOR_LOST_BULLET)
    if t["is_bot"]:
        lines.append(f"- 🤖 Comment is from a bot ({t['first_comment']['author']}).")
    lines.append(f"- **Author:** {t['first_comment']['author']} ({t['first_comment']['created_at']})")
    lines.append(f"- **Comment:** {t['first_comment']['body']}")
    lines.append(f"- **URL:** {t['url']}")
    lines.append(f"- **Thread ID:** `{t['id']}`")
    if t["replies"]:
        last_author = t["replies"][-1]["author"]
        lines.append(f"- **Replies:** {len(t['replies'])} (latest from {last_author})")
    lines.append("")  # blank line between threads
    return lines


def render(payload: dict) -> str:
    ctx = payload["context"]
    counts = payload["counts"]
    active = payload["active"]

    lines: list[str] = []
    lines.append(f"# PR #{ctx['pr_number']} — Active Review Threads")
    lines.append("")
    lines.append(f"**Provider:** {ctx['provider_display']}")
    lines.append(f"**Branch:** {ctx['branch']}")
    lines.append(f"**PR:** {ctx['pr_url']}")
    lines.append(
        f"**Status counts:** {counts['active']} active, "
        f"{counts['pending']} pending, "
        f"{counts['resolved']} resolved (deliberate — not shown)"
    )
    lines.append("")
    lines.append(f"**Detailed JSON:** `./docs/pr/{ctx['pr_number']}-active.json`")
    lines.append("")
    lines.append("## Active threads")
    lines.append("")
    if not active:
        lines.append("_No active threads._")
        lines.append("")
    else:
        for i, t in enumerate(active, start=1):
            lines.extend(render_thread(i, t))
    lines.append("---")
    lines.append("")
    lines.append(NEXT_STEPS)
    return "\n".join(lines)


def main() -> int:
    payload = json.load(sys.stdin)
    sys.stdout.write(render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
