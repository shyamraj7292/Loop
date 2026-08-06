"""Tests for canonical URLs and simhash — no DB or model required."""

from __future__ import annotations

from loop.pipeline.dedup import (
    canonical_url,
    hamming_distance,
    is_near_duplicate,
    simhash,
    to_signed64,
    to_unsigned64,
)


def test_canonical_strips_tracking_params():
    url = "https://www.example.com/news/story/?utm_source=twitter&id=42&utm_medium=x"
    assert canonical_url(url) == "https://example.com/news/story?id=42"


def test_canonical_sorts_query_and_drops_fragment():
    a = canonical_url("https://example.com/a?b=2&a=1#section")
    b = canonical_url("https://example.com/a?a=1&b=2")
    assert a == b


def test_canonical_lowercases_host_and_strips_www():
    assert canonical_url("HTTPS://WWW.Example.COM/Path/") == "https://example.com/Path"


def test_simhash_fits_signed_bigint():
    h = simhash("the reserve bank of india held the repo rate steady today")
    assert -(2**63) <= h < 2**63


def test_signed_unsigned_roundtrip():
    for value in (0, 1, 2**63 - 1, 2**63, 2**64 - 1):
        signed = to_signed64(value)
        assert to_unsigned64(signed) == (value & ((1 << 64) - 1))


def test_near_duplicate_detection():
    # Simhash near-dup detection targets article-length wire copy, not short
    # headlines: the same PTI story republished with a trailing sentence.
    a = (
        "The Reserve Bank of India kept the benchmark repo rate unchanged at 6.25 "
        "percent on Wednesday and changed its policy stance to neutral, citing "
        "easing inflation and a need to support growth as global uncertainty "
        "weighs on the domestic economy."
    )
    b = a + " Analysts had widely expected the decision."
    c = (
        "India chased down the target with six wickets in hand to level the "
        "one-day series against Australia, powered by a fluent century from the "
        "opener at Rajkot on Sunday."
    )
    ha, hb, hc = simhash(a), simhash(b), simhash(c)
    assert is_near_duplicate(ha, hb)
    assert not is_near_duplicate(ha, hc)
    assert hamming_distance(ha, ha) == 0
