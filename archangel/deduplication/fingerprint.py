"""Fingerprinting, feature extraction, and similarity calculation for lead deduplication."""

import hashlib
import re
from difflib import SequenceMatcher
from typing import Dict, Set

from archangel.models import RawPost

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
URL_REGEX = re.compile(r"https?://[^\s]+")


def normalize_text(text: str) -> str:
    """Clean text by removing emails, URLs, special characters, and normalizing whitespace."""
    if not text:
        return ""
    cleaned = EMAIL_REGEX.sub("", text)
    cleaned = URL_REGEX.sub("", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned).lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_post_keys(post: RawPost) -> Dict[str, Set[str]]:
    """Extract deterministic identity keys (emails, URLs, content SHA256) from a RawPost."""
    content = post.content or ""
    emails = set(EMAIL_REGEX.findall(content))
    urls = set(URL_REGEX.findall(content))

    clean_str = normalize_text(content)
    content_hash = (
        hashlib.sha256(clean_str.encode("utf-8")).hexdigest()
        if clean_str
        else ""
    )

    return {
        "emails": emails,
        "urls": urls,
        "content_hash": {content_hash} if content_hash else set(),
    }


def compute_post_similarity(post1: RawPost, post2: RawPost) -> float:
    """Compute combined Jaccard & Sequence similarity ratio [0.0, 1.0] between two posts."""
    keys1 = extract_post_keys(post1)
    keys2 = extract_post_keys(post2)

    # Shortcut: Exact key matches (email or URL match)
    if (keys1["emails"] and keys1["emails"] & keys2["emails"]) or (
        keys1["urls"] and keys1["urls"] & keys2["urls"]
    ):
        return 1.0

    t1 = normalize_text(post1.content or "")
    t2 = normalize_text(post2.content or "")

    if not t1 or not t2:
        return 0.0

    if t1 == t2:
        return 1.0

    # Sequence similarity
    seq_sim = SequenceMatcher(None, t1, t2).ratio()

    # Token Jaccard similarity
    tokens1 = set(t1.split())
    tokens2 = set(t2.split())
    union = tokens1 | tokens2
    jaccard_sim = len(tokens1 & tokens2) / len(union) if union else 0.0

    # Weighted combination
    return round(0.6 * seq_sim + 0.4 * jaccard_sim, 4)
