"""Claim grounding validator (README > Security model).

Every claim must carry `source_article_ids`; claims with empty support are
dropped. Output is also scanned for instruction-like patterns before storage, in
case a prompt injection made it through the model into a claim.
"""

from __future__ import annotations

import logging
import re

from loop.llm.base import Claim

logger = logging.getLogger(__name__)

# Phrases that should never legitimately appear in a factual news claim — a
# strong signal that article content leaked model-directed text into output.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all |the )?(previous|prior|above) instructions", re.I),
    re.compile(r"disregard (all |the )?(previous|prior|above)", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"you are (now |an? )?(ai|assistant|chatbot|language model)", re.I),
    re.compile(r"as an ai (language )?model", re.I),
    re.compile(r"\bBEGIN\s+(UNTRUSTED|SYSTEM)\b", re.I),
]


def _looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def validate_claims(claims: list[Claim], allowed_article_ids: set[int]) -> list[Claim]:
    """Keep only well-grounded, non-suspicious claims.

    A claim survives iff it has at least one supporting article that actually
    belongs to this story, and it doesn't look like leaked instructions.
    """
    kept: list[Claim] = []
    for claim in claims:
        support = [a for a in claim.source_article_ids if a in allowed_article_ids]
        if not support:
            logger.info("Dropping ungrounded claim: %s", claim.text[:120])
            continue
        if _looks_like_injection(claim.text):
            logger.warning("Dropping injection-like claim: %s", claim.text[:120])
            continue
        kept.append(claim.model_copy(update={"source_article_ids": support}))
    return kept
