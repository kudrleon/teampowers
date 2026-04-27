#!/usr/bin/env python3
"""Filter normalized threads: drop pending/resolved, emit {active, counts}.

stdin:  JSON array of normalized threads (see references/normalized-schema.md).
stdout: JSON object {"active": [...], "counts": {...}}.
"""
import json
import sys
from collections import Counter


def filter_threads(threads: list[dict]) -> dict:
    counts = Counter(t["status"] for t in threads)
    return {
        "active": [t for t in threads if t["status"] == "active"],
        "counts": {
            "total":    len(threads),
            "active":   counts.get("active", 0),
            "pending":  counts.get("pending", 0),
            "resolved": counts.get("resolved", 0),
        },
    }


def main() -> int:
    threads = json.load(sys.stdin)
    result = filter_threads(threads)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
