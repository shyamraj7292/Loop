"""Clustering metrics: B-cubed precision/recall/F1 and cluster purity.

B-cubed is the standard for this task (README > Clustering quality); it comes
from the coreference-resolution community. These functions are pure so they can
be unit-tested without a database or a model.

Inputs are two parallel lists: predicted[i] and gold[i] are the cluster labels
assigned to item i by the system and by the hand-labelled gold set.
"""

from __future__ import annotations

from collections import Counter, defaultdict


def _check(pred: list, gold: list) -> None:
    if len(pred) != len(gold):
        raise ValueError("pred and gold must be the same length")
    if not pred:
        raise ValueError("empty input")


def bcubed_precision_recall_f1(
    pred: list, gold: list
) -> tuple[float, float, float]:
    _check(pred, gold)
    n = len(pred)

    pred_members: dict = defaultdict(list)
    gold_members: dict = defaultdict(list)
    for i in range(n):
        pred_members[pred[i]].append(i)
        gold_members[gold[i]].append(i)

    precision_sum = 0.0
    recall_sum = 0.0
    for i in range(n):
        same_pred = set(pred_members[pred[i]])
        same_gold = set(gold_members[gold[i]])
        correct = len(same_pred & same_gold)
        precision_sum += correct / len(same_pred)
        recall_sum += correct / len(same_gold)

    precision = precision_sum / n
    recall = recall_sum / n
    f1 = (
        0.0
        if precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )
    return precision, recall, f1


def purity(pred: list, gold: list) -> float:
    """Fraction of items in the majority gold class of their predicted cluster."""
    _check(pred, gold)
    n = len(pred)
    clusters: dict = defaultdict(list)
    for i in range(n):
        clusters[pred[i]].append(gold[i])
    total = sum(Counter(members).most_common(1)[0][1] for members in clusters.values())
    return total / n
