"""Tests for the clustering metric harness — pure, no model/DB."""

from __future__ import annotations

import pytest

from evals.metrics import bcubed_precision_recall_f1, purity


def test_perfect_clustering():
    pred = [0, 0, 1, 1]
    gold = ["a", "a", "b", "b"]
    p, r, f1 = bcubed_precision_recall_f1(pred, gold)
    assert p == pytest.approx(1.0)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(1.0)
    assert purity(pred, gold) == pytest.approx(1.0)


def test_oversplit_is_precise_not_recallful():
    # Every item in its own cluster: precision perfect, recall poor.
    pred = [0, 1, 2, 3]
    gold = ["a", "a", "b", "b"]
    p, r, _ = bcubed_precision_recall_f1(pred, gold)
    assert p == pytest.approx(1.0)
    assert r < 1.0


def test_merged_is_recallful_not_precise():
    # Everything in one cluster: recall perfect, precision poor.
    pred = [0, 0, 0, 0]
    gold = ["a", "a", "b", "b"]
    p, r, _ = bcubed_precision_recall_f1(pred, gold)
    assert r == pytest.approx(1.0)
    assert p < 1.0


def test_purity_partial():
    pred = [0, 0, 0]
    gold = ["a", "a", "b"]
    assert purity(pred, gold) == pytest.approx(2 / 3)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        bcubed_precision_recall_f1([0, 1], ["a"])
