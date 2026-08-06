"""Faithfulness eval.

    python -m evals.faithfulness --sample 100

The real test is human: sample generated claims and verify each against its cited
source articles, targeting a hallucination rate < 2% and categorising failures
(unsupported inference, entity swap, temporal error, conflation). That human loop
can't be automated away.

What this script *does* automate is the grounding precondition — every claim must
carry at least one supporting article that actually belongs to its story. It
samples stored claims and reports the grounded fraction, then writes a review
sheet for the manual pass.
"""

from __future__ import annotations

import argparse
import csv
import random

from sqlalchemy import select

from loop.db import session_scope
from loop.models import Event, StoryArticle


def run(sample: int, out_path: str | None) -> None:
    with session_scope() as session:
        events = list(
            session.execute(select(Event)).scalars().all()
        )
        claims: list[tuple[int, dict]] = []
        for event in events:
            for claim in event.claims or []:
                claims.append((event.story_id, claim))

        if not claims:
            print("No claims found. Run the pipeline first.")
            return

        random.shuffle(claims)
        chosen = claims[:sample]

        grounded = 0
        rows = []
        for story_id, claim in chosen:
            story_article_ids = set(
                session.execute(
                    select(StoryArticle.article_id).where(
                        StoryArticle.story_id == story_id
                    )
                ).scalars().all()
            )
            support = [
                a
                for a in claim.get("source_article_ids", [])
                if a in story_article_ids
            ]
            is_grounded = bool(support)
            grounded += 1 if is_grounded else 0
            rows.append(
                {
                    "story_id": story_id,
                    "claim": claim.get("text", ""),
                    "support_article_ids": ";".join(map(str, support)),
                    "grounded": is_grounded,
                    "human_verdict": "",  # fill in during manual review
                    "failure_category": "",
                }
            )

    n = len(chosen)
    print(f"Sampled {n} claim(s).")
    print(f"Grounded (has valid supporting article): {grounded}/{n} = {grounded / n:.1%}")
    print("Ungrounded claims are a hard bug — they should never have been stored.")
    print("For the real hallucination rate, verify each claim by hand.")

    if out_path:
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote review sheet: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Faithfulness eval.")
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--out", default="evals/faithfulness_review.csv")
    args = parser.parse_args()
    run(args.sample, args.out)


if __name__ == "__main__":
    main()
