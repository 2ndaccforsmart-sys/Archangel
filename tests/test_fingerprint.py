from archangel.deduplication.fingerprint import (
    compute_post_similarity,
    extract_post_keys,
    normalize_text,
)
from archangel.models import RawPost


def test_normalize_text():
    raw = "Need Python Dev! Contact: test@example.com https://example.com/job"
    normalized = normalize_text(raw)
    assert "test@example.com" not in normalized
    assert "https://" not in normalized
    assert "python dev" in normalized


def test_extract_post_keys():
    post = RawPost(content="Hire me test@domain.com https://github.com/myrepo")
    keys = extract_post_keys(post)
    assert "test@domain.com" in keys["emails"]
    assert "https://github.com/myrepo" in keys["urls"]


def test_compute_post_similarity_exact_match():
    p1 = RawPost(content="Looking for a Python senior backend engineer to build API endpoints fast")
    p2 = RawPost(content="Looking for a Python senior backend engineer to build API endpoints fast")
    sim = compute_post_similarity(p1, p2)
    assert sim >= 0.99


def test_compute_post_similarity_email_shortcut():
    p1 = RawPost(content="Hiring dev contact us at jobs@acme.org")
    p2 = RawPost(content="We need developers urgently, send resume to jobs@acme.org please")
    sim = compute_post_similarity(p1, p2)
    assert sim == 1.0


def test_compute_post_similarity_different():
    p1 = RawPost(content="Need React frontend dev for mobile responsive landing page")
    p2 = RawPost(content="Hiring Rust embedded systems developer for microcontrollers")
    sim = compute_post_similarity(p1, p2)
    assert sim < 0.3
