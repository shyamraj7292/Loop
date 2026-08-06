"""Canonical URLs and simhash near-duplicate detection.

Not optional in the Indian context (README > Normalise and deduplicate): one PTI
or ANI wire story appears verbatim in forty outlets. Without dedup, wire copy
dominates every cluster and the importance signal becomes noise.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query params that are pure tracking noise and should never affect identity.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_reader",
    "fbclid",
    "gclid",
    "dclid",
    "gbraid",
    "wbraid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "cmpid",
    "cid",
    "ncid",
    "ref",
    "ref_src",
    "source",
    "spm",
}

_MASK64 = (1 << 64) - 1
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def canonical_url(url: str) -> str:
    """Normalise a URL for identity: strip tracking params and fragments,
    lowercase the host, and sort the surviving query so ordering can't create
    a false 'new' article."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/") or "/"

    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS
    ]
    kept.sort()
    query = urlencode(kept)

    return urlunparse((scheme, netloc, path, "", query, ""))


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def simhash(text: str, *, ngram: int = 3) -> int:
    """64-bit simhash over word n-grams. Returned as a SIGNED 64-bit int so it
    fits a Postgres BIGINT (see to_signed64)."""
    tokens = _tokens(text)
    if not tokens:
        return 0

    shingles: list[str] = (
        [" ".join(tokens[i : i + ngram]) for i in range(len(tokens) - ngram + 1)]
        if len(tokens) >= ngram
        else tokens
    )

    vector = [0] * 64
    for shingle in shingles:
        h = int.from_bytes(
            hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(),
            "big",
        )
        for bit in range(64):
            vector[bit] += 1 if (h >> bit) & 1 else -1

    fingerprint = 0
    for bit in range(64):
        if vector[bit] > 0:
            fingerprint |= 1 << bit
    return to_signed64(fingerprint)


def to_signed64(value: int) -> int:
    """Map an unsigned 64-bit value into signed BIGINT range."""
    value &= _MASK64
    return value - (1 << 64) if value >= (1 << 63) else value


def to_unsigned64(value: int) -> int:
    """Recover the unsigned 64-bit representation from a signed BIGINT."""
    return value & _MASK64


def hamming_distance(a: int, b: int) -> int:
    return bin((to_unsigned64(a) ^ to_unsigned64(b))).count("1")


def is_near_duplicate(a: int, b: int, *, threshold: int = 3) -> bool:
    """Two simhashes within `threshold` bits are near-duplicates (wire copy)."""
    return hamming_distance(a, b) <= threshold
