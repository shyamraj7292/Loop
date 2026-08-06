"""Clustering quality eval.

    python -m evals.clustering --gold evals/gold_clusters.jsonl
    python -m evals.clustering --quick     # fast self-test of the metric harness

Runs the same online, centroid-matching clustering the pipeline uses (in memory,
no DB) over hand-labelled articles, then reports B-cubed P/R/F1 and purity.
Report the failure breakdown by topic too: sports clusters tighter than politics,
so a single global threshold will underperform (README > Clustering quality).
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from evals.metrics import bcubed_precision_recall_f1, purity


def _online_cluster(vectors: list[list[float]], threshold: float) -> list[int]:
    """Greedy online clustering mirroring loop.pipeline.cluster."""
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels: list[int] = []
    for vec in vectors:
        v = np.asarray(vec, dtype=np.float32)
        v = v / (np.linalg.norm(v) or 1.0)
        best_idx, best_sim = -1, -1.0
        for idx, c in enumerate(centroids):
            sim = float(np.dot(v, c))
            if sim > best_sim:
                best_idx, best_sim = idx, sim
        if best_idx >= 0 and best_sim >= threshold:
            labels.append(best_idx)
            n = counts[best_idx]
            merged = (centroids[best_idx] * n + v) / (n + 1)
            centroids[best_idx] = merged / (np.linalg.norm(merged) or 1.0)
            counts[best_idx] += 1
        else:
            labels.append(len(centroids))
            centroids.append(v)
            counts.append(1)
    return labels


def run_gold(path: str, threshold: float) -> None:
    from loop.pipeline.embed import article_embedding_text, embed_texts

    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("Gold file is empty.")
        return

    texts = [article_embedding_text(r.get("title"), r.get("text")) for r in rows]
    gold = [r["gold_story"] for r in rows]

    print(f"Embedding {len(texts)} article(s) with the pipeline model...")
    vectors = embed_texts(texts)
    pred = _online_cluster(vectors, threshold)

    p, r, f1 = bcubed_precision_recall_f1(pred, gold)
    pur = purity(pred, gold)
    print(f"\nthreshold        {threshold}")
    print(f"predicted clusters {len(set(pred))}  |  gold clusters {len(set(gold))}")
    print(f"B-cubed precision  {p:.3f}")
    print(f"B-cubed recall     {r:.3f}")
    print(f"B-cubed F1         {f1:.3f}")
    print(f"cluster purity     {pur:.3f}")


def run_quick() -> None:
    """No model, no DB: verify the metric harness on a known toy example."""
    pred = [0, 0, 1, 1, 2]
    gold = ["a", "a", "b", "b", "b"]
    p, r, f1 = bcubed_precision_recall_f1(pred, gold)
    pur = purity(pred, gold)
    print("quick self-test (toy labels):")
    print(f"  B-cubed P/R/F1 = {p:.3f}/{r:.3f}/{f1:.3f}  purity = {pur:.3f}")
    assert abs(p - 1.0) < 1e-9, "precision should be perfect for pure predicted clusters"
    print("  OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clustering quality eval.")
    parser.add_argument("--gold", default="evals/gold_clusters.jsonl")
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    if args.quick:
        run_quick()
    else:
        run_gold(args.gold, args.threshold)


if __name__ == "__main__":
    main()
