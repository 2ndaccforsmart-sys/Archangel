# Smart Deduplication & Merging Design Document

**Date:** 2026-07-23  
**Feature:** Smart Deduplication & Merging (Approach D - Two-Tier Hybrid Engine)  
**Status:** Approved  

---

## 1. Overview

Archangel ingests leads from multiple channels (Reddit, Discord, GitHub, Telegram). Often, the same job or opportunity is cross-posted across multiple channels. 

The Smart Deduplication Engine detects cross-posted leads before or during analysis, merging duplicates into a single canonical lead record while maintaining source links and full post context.

---

## 2. Architecture & Design (Approach D - Two-Tier Engine)

### Two-Tier Hybrid Pipeline
1. **Tier 1 (Deterministic & Similarity Pre-Filter):**
   - **Exact Keys:** Compares clean URL, normalized email, external links, and SHA256 content hashes. Match score = 1.0.
   - **Text Similarity:** Calculates normalized sequence similarity and token Jaccard similarity over post titles/contents (last 7 days window).
   - **Decision Rules:**
     - Score >= 0.88 or Exact Key match: **Auto-Merge** into canonical lead.
     - Score < 0.50: **Distinct Lead** (pass through).
     - Score between 0.50 and 0.88: **Escalate to Tier 2**.

2. **Tier 2 (LLM Verification):**
   - Prompts LLM for borderline cases: "Do post A and post B represent the exact same hiring need/opportunity?"
   - LLM responds with `is_match: bool`, `confidence: float`, `reason: str`.
   - If `is_match` is true and `confidence >= 0.70`, merge into canonical lead; otherwise keep distinct.

---

## 3. Data Model & DB Schema Updates

### SQLite Schema (`archangel/storage/__init__.py`)

```sql
CREATE TABLE IF NOT EXISTS lead_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_lead_id INTEGER NOT NULL,
    raw_post_id INTEGER NOT NULL UNIQUE,
    merged_at TEXT DEFAULT CURRENT_TIMESTAMP,
    confidence REAL,
    merge_reason TEXT,
    tier_used TEXT,
    FOREIGN KEY (raw_post_id) REFERENCES raw_posts(id)
);
```

Add `canonical_lead_id` indexing and multi-source querying support in `StorageBackend`.

---

## 4. Components

1. `archangel/deduplication/fingerprint.py`
   - Normalization helpers (strip URLs, emails, symbols, lowercase).
   - `extract_keys(post)` -> `{emails, urls, links, hash}`.
   - `calculate_similarity(post_a, post_b)` -> float `[0.0, 1.0]`.

2. `archangel/deduplication/engine.py`
   - `DeduplicationEngine.evaluate_post(post, window_days=7)` -> `DeduplicationResult(action: "merge" | "create", target_lead_id: int | None, confidence: float, reason: str, tier: str)`.

3. `archangel/deduplication/agent.py`
   - `DeduplicationAgent` subscribing to `raw_post.stored` event and publishing `lead.deduped` or `lead.merged`.

4. `archangel/cli/` update
   - `archangel duplicates`
   - `archangel merge <lead_id1> <lead_id2>`
   - `archangel unmerge <lead_id> <post_id>`

---

## 5. Testing & Verification

- Unit tests for fingerprinting and text similarity calculation (`tests/test_fingerprint.py`).
- Integration tests for two-tier deduplication engine (`tests/test_deduplication.py`).
- Storage tests for `lead_sources` queries.
