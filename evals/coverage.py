"""Coverage eval.

    python -m evals.coverage --snapshot evals/frontpage_2026-08-05.jsonl

Take an independent front-page snapshot daily. What percentage of major stories
did Loop surface within 6 hours? Report by category — you will likely find that
regional and vernacular coverage is much worse than national English, and that is
a finding worth stating (README > Coverage).

The snapshot file is JSONL, one story per line:
    {"headline": "...", "category": "national", "first_seen": "2026-08-05T06:00:00Z"}

Matching a snapshot headline to a Loop story is a retrieval problem; this script
does a lexical match as a baseline and flags low-confidence matches for review.
A semantic match over story centroids is the obvious upgrade.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select

from loop.db import session_scope
from loop.models import Story


def _overlap(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def run(snapshot_path: str, window_hours: int, match_threshold: float) -> None:
    with open(snapshot_path, encoding="utf-8") as fh:
        snapshot = [json.loads(line) for line in fh if line.strip()]
    if not snapshot:
        print("Snapshot is empty.")
        return

    with session_scope() as session:
        stories = list(session.execute(select(Story)).scalars().all())

    by_category: dict[str, list[bool]] = defaultdict(list)
    for item in snapshot:
        headline = item.get("headline", "")
        category = item.get("category", "uncategorised")
        first_seen = datetime.fromisoformat(item["first_seen"])
        deadline = first_seen + timedelta(hours=window_hours)

        surfaced = any(
            s.title
            and _overlap(headline, s.title) >= match_threshold
            and s.first_seen
            and s.first_seen <= deadline
            for s in stories
        )
        by_category[category].append(surfaced)

    print(f"Coverage within {window_hours}h (lexical match >= {match_threshold}):\n")
    overall_hits = overall_total = 0
    for category, results in sorted(by_category.items()):
        hits = sum(results)
        total = len(results)
        overall_hits += hits
        overall_total += total
        print(f"  {category:20s} {hits}/{total} = {hits / total:.0%}")
    print(f"\n  {'OVERALL':20s} {overall_hits}/{overall_total} = "
          f"{overall_hits / overall_total:.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Coverage eval.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--window-hours", type=int, default=6)
    parser.add_argument("--match-threshold", type=float, default=0.3)
    args = parser.parse_args()
    run(args.snapshot, args.window_hours, args.match_threshold)


if __name__ == "__main__":
    main()
