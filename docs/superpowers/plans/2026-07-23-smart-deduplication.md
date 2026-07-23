# Smart Deduplication & Merging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Two-Tier Hybrid Deduplication Engine (Approach D) that identifies cross-posted leads across Reddit, Discord, GitHub, and Telegram, merging duplicates into a canonical lead profile with linked sources.

**Architecture:** 
`archangel/deduplication/fingerprint.py` extracts normalized tokens/metadata and calculates text Jaccard & SequenceMatcher similarity. 
`archangel/deduplication/engine.py` executes Tier 1 (fast similarity & exact key match) and Tier 2 (LLM verification for borderline 0.50-0.88 similarity cases).
`archangel/storage/__init__.py` persists `lead_sources` table and updates queries.
`archangel/deduplication/agent.py` subscribes to `raw_post.stored` events to perform automated deduplication.

**Tech Stack:** Python 3.12, SQLite (WAL), stdlib (`difflib`, `re`, `hashlib`), `pytest`.

---

### Task 1: Fingerprint & Similarity Calculator

**Files:**
- Create: `archangel/deduplication/__init__.py`
- Create: `archangel/deduplication/fingerprint.py`
- Create: `tests/test_fingerprint.py`

- [ ] **Step 1: Write failing tests for text normalization and similarity calculation**

```python
# tests/test_fingerprint.py
from archangel.deduplication.fingerprint import normalize_text, extract_post_keys, compute_post_similarity
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

def test_compute_post_similarity_different():
    p1 = RawPost(content="Need React frontend dev for mobile responsive landing page")
    p2 = RawPost(content="Hiring Rust embedded systems developer for microcontrollers")
    sim = compute_post_similarity(p1, p2)
    assert sim < 0.3
```

- [ ] **Step 2: Run pytest to verify failure**

Run: `pytest tests/test_fingerprint.py`
Expected: FAIL (ModuleNotFoundError / ImportError)

- [ ] **Step 3: Implement fingerprint normalization and similarity calculation**

```python
# archangel/deduplication/__init__.py
"""Smart Deduplication Package for The Archangel."""

# archangel/deduplication/fingerprint.py
import re
import hashlib
from typing import Any, Dict, Set
from difflib import SequenceMatcher
from archangel.models import RawPost

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
URL_REGEX = re.compile(r'https?://[^\s]+')

def normalize_text(text: str) -> str:
    cleaned = EMAIL_REGEX.sub('', text)
    cleaned = URL_REGEX.sub('', cleaned)
    cleaned = re.sub(r'[^\w\s]', ' ', cleaned).lower()
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_post_keys(post: RawPost) -> Dict[str, Set[str]]:
    content = post.content or ""
    emails = set(EMAIL_REGEX.findall(content))
    urls = set(URL_REGEX.findall(content))
    
    clean_str = normalize_text(content)
    content_hash = hashlib.sha256(clean_str.encode('utf-8')).hexdigest() if clean_str else ""
    
    return {
        "emails": emails,
        "urls": urls,
        "content_hash": {content_hash} if content_hash else set(),
    }

def compute_post_similarity(post1: RawPost, post2: RawPost) -> float:
    keys1 = extract_post_keys(post1)
    keys2 = extract_post_keys(post2)
    
    # Exact key match shortcut
    if (keys1["emails"] & keys2["emails"]) or (keys1["urls"] & keys2["urls"]):
        return 1.0
        
    t1 = normalize_text(post1.content or "")
    t2 = normalize_text(post2.content or "")
    
    if not t1 or not t2:
        return 0.0
        
    if t1 == t2:
        return 1.0
        
    matcher = SequenceMatcher(None, t1, t2)
    seq_sim = matcher.ratio()
    
    tokens1 = set(t1.split())
    tokens2 = set(t2.split())
    union = tokens1 | tokens2
    jaccard_sim = len(tokens1 & tokens2) / len(union) if union else 0.0
    
    return round(0.6 * seq_sim + 0.4 * jaccard_sim, 4)
```

- [ ] **Step 4: Run pytest to verify pass**

Run: `pytest tests/test_fingerprint.py`
Expected: PASS

---

### Task 2: Database Schema & Source Persistence

**Files:**
- Modify: `archangel/storage/__init__.py`
- Create: `tests/test_dedup_storage.py`

- [ ] **Step 1: Write failing tests for lead_sources table and canonical link helpers**

```python
# tests/test_dedup_storage.py
import pytest
from pathlib import Path
from archangel.storage import StorageBackend
from archangel.models import RawPost

@pytest.fixture
def tmp_storage(tmp_path):
    db_file = tmp_path / "test_archangel.db"
    storage = StorageBackend(db_path=db_file)
    yield storage
    storage.close()

def test_lead_sources_table_and_merge(tmp_storage):
    post1 = RawPost(source="reddit", content="Need Dev", url="http://reddit.com/1")
    post2 = RawPost(source="discord", content="Need Dev", url="http://discord.com/1")
    
    id1 = tmp_storage.store_raw_post(post1)
    id2 = tmp_storage.store_raw_post(post2)
    
    tmp_storage.link_lead_source(canonical_lead_id=id1, raw_post_id=id2, confidence=0.95, merge_reason="high similarity", tier_used="tier1")
    
    sources = tmp_storage.get_lead_sources(canonical_lead_id=id1)
    assert len(sources) == 1
    assert sources[0]["raw_post_id"] == id2
    assert sources[0]["confidence"] == 0.95
```

- [ ] **Step 2: Run pytest to verify failure**

Run: `pytest tests/test_dedup_storage.py`
Expected: FAIL (`AttributeError: 'StorageBackend' object has no attribute 'link_lead_source'`)

- [ ] **Step 3: Update `StorageBackend` to create `lead_sources` table and add query helpers**

Add table to `_create_tables` in `archangel/storage/__init__.py`:
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

Add methods to `StorageBackend`:
```python
def link_lead_source(self, canonical_lead_id: int, raw_post_id: int, confidence: float = 1.0, merge_reason: str = "", tier_used: str = "tier1") -> int:
    with self._write_lock:
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """INSERT OR REPLACE INTO lead_sources (canonical_lead_id, raw_post_id, confidence, merge_reason, tier_used)
                   VALUES (?, ?, ?, ?, ?)""",
                (canonical_lead_id, raw_post_id, confidence, merge_reason, tier_used)
            )
            self._conn.commit()
            return cursor.lastrowid or 0
        except Exception as exc:
            logger.error("link_lead_source failed: %s", exc)
            return 0

def get_lead_sources(self, canonical_lead_id: int) -> List[dict[str, Any]]:
    with self._write_lock:
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM lead_sources WHERE canonical_lead_id = ? ORDER BY merged_at ASC",
                (canonical_lead_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("get_lead_sources failed: %s", exc)
            return []
```

- [ ] **Step 4: Run pytest to verify pass**

Run: `pytest tests/test_dedup_storage.py`
Expected: PASS

---

### Task 3: Two-Tier Deduplication Engine

**Files:**
- Create: `archangel/deduplication/engine.py`
- Create: `tests/test_dedup_engine.py`

- [ ] **Step 1: Write failing tests for Tier 1 and Tier 2 deduplication logic**

```python
# tests/test_dedup_engine.py
from archangel.deduplication.engine import DeduplicationEngine, DeduplicationResult
from archangel.models import RawPost

def test_engine_tier1_auto_merge(tmp_path):
    from archangel.storage import StorageBackend
    storage = StorageBackend(db_path=tmp_path / "test.db")
    engine = DeduplicationEngine(storage=storage)
    
    p1 = RawPost(source="reddit", content="Need senior Python engineer for FastAPI microservices", url="http://reddit.com/job1")
    id1 = storage.store_raw_post(p1)
    p1.id = id1
    
    p2 = RawPost(source="discord", content="Need senior Python engineer for FastAPI microservices", url="http://discord.com/job1")
    id2 = storage.store_raw_post(p2)
    p2.id = id2
    
    res = engine.evaluate_post(p2, candidates=[p1])
    assert res.action == "merge"
    assert res.target_lead_id == id1
    assert res.tier == "tier1"
    storage.close()

def test_engine_distinct_lead(tmp_path):
    from archangel.storage import StorageBackend
    storage = StorageBackend(db_path=tmp_path / "test.db")
    engine = DeduplicationEngine(storage=storage)
    
    p1 = RawPost(source="reddit", content="Need React dev", url="http://reddit.com/react")
    p1.id = storage.store_raw_post(p1)
    
    p2 = RawPost(source="github", content="Hiring Rust developer for WebAssembly compiler", url="http://github.com/rust")
    p2.id = storage.store_raw_post(p2)
    
    res = engine.evaluate_post(p2, candidates=[p1])
    assert res.action == "create"
    assert res.target_lead_id is None
    storage.close()
```

- [ ] **Step 2: Run pytest to verify failure**

Run: `pytest tests/test_dedup_engine.py`
Expected: FAIL

- [ ] **Step 3: Implement `DeduplicationEngine` class**

```python
# archangel/deduplication/engine.py
from dataclasses import dataclass
from typing import List, Optional, Callable
from archangel.models import RawPost
from archangel.deduplication.fingerprint import compute_post_similarity
from archangel.storage import StorageBackend

@dataclass
class DeduplicationResult:
    action: str  # "merge" or "create"
    target_lead_id: Optional[int]
    confidence: float
    reason: str
    tier: str

class DeduplicationEngine:
    def __init__(self, storage: Optional[StorageBackend] = None, llm_verifier: Optional[Callable[[RawPost, RawPost], bool]] = None) -> None:
        self.storage = storage or StorageBackend.get_instance()
        self.llm_verifier = llm_verifier

    def evaluate_post(self, new_post: RawPost, candidates: Optional[List[RawPost]] = None) -> DeduplicationResult:
        if candidates is None:
            raw_leads = self.storage.get_leads(limit=100)
            candidates = [
                RawPost(
                    source=r["source"],
                    channel=r.get("channel", ""),
                    author=r.get("author", ""),
                    content=r["content"],
                    url=r["url"],
                    metadata={},
                )
                for r in raw_leads if r.get("id") != new_post.id
            ]
            for idx, c in enumerate(candidates):
                c.id = raw_leads[idx]["id"]

        best_candidate = None
        best_sim = 0.0

        for cand in candidates:
            sim = compute_post_similarity(new_post, cand)
            if sim > best_sim:
                best_sim = sim
                best_candidate = cand

        # Tier 1 decisions
        if best_sim >= 0.88 and best_candidate:
            return DeduplicationResult(
                action="merge",
                target_lead_id=best_candidate.id,
                confidence=best_sim,
                reason=f"High similarity ({best_sim:.2f}) with post #{best_candidate.id}",
                tier="tier1",
            )
            
        if best_sim < 0.50 or not best_candidate:
            return DeduplicationResult(
                action="create",
                target_lead_id=None,
                confidence=1.0 - best_sim,
                reason="No candidate reached minimum similarity threshold (0.50)",
                tier="tier1",
            )

        # Tier 2 decisions (Grey area: 0.50 <= best_sim < 0.88)
        if self.llm_verifier:
            is_match = self.llm_verifier(new_post, best_candidate)
            if is_match:
                return DeduplicationResult(
                    action="merge",
                    target_lead_id=best_candidate.id,
                    confidence=0.85,
                    reason=f"LLM verified match with post #{best_candidate.id}",
                    tier="tier2",
                )

        return DeduplicationResult(
            action="create",
            target_lead_id=None,
            confidence=0.70,
            reason=f"Similarity in grey zone ({best_sim:.2f}) but LLM did not verify match",
            tier="tier2" if self.llm_verifier else "tier1_fallback",
        )
```

- [ ] **Step 4: Run pytest to verify pass**

Run: `pytest tests/test_dedup_engine.py`
Expected: PASS

---

### Task 4: DeduplicationAgent Event Integration

**Files:**
- Create: `archangel/deduplication/agent.py`
- Create: `tests/test_dedup_agent.py`

- [ ] **Step 1: Write failing test for `DeduplicationAgent` event subscription**

```python
# tests/test_dedup_agent.py
from archangel.events import EventBus
from archangel.deduplication.agent import DeduplicationAgent
from archangel.storage import StorageBackend
from archangel.models import RawPost

def test_deduplication_agent_event_flow(tmp_path):
    bus = EventBus()
    storage = StorageBackend(db_path=tmp_path / "test.db")
    agent = DeduplicationAgent(event_bus=bus, storage=storage)
    
    p1 = RawPost(source="reddit", content="Need Python developer for AI bot", url="http://reddit.com/bot1")
    id1 = storage.store_raw_post(p1)
    
    events_received = []
    bus.subscribe("lead.*", lambda payload: events_received.append(payload))
    
    p2 = RawPost(source="discord", content="Need Python developer for AI bot", url="http://discord.com/bot1")
    id2 = storage.store_raw_post(p2)
    p2.id = id2
    
    bus.publish("raw_post.stored", {"post": p2, "raw_post_id": id2})
    
    assert len(events_received) > 0
    assert any(e.get("action") == "merged" for e in events_received)
    storage.close()
```

- [ ] **Step 2: Run pytest to verify failure**

Run: `pytest tests/test_dedup_agent.py`
Expected: FAIL

- [ ] **Step 3: Implement `DeduplicationAgent`**

```python
# archangel/deduplication/agent.py
import logging
from typing import Optional
from archangel.events import EventBus
from archangel.storage import StorageBackend
from archangel.models import RawPost
from archangel.deduplication.engine import DeduplicationEngine

logger = logging.getLogger(__name__)

class DeduplicationAgent:
    def __init__(self, event_bus: Optional[EventBus] = None, storage: Optional[StorageBackend] = None) -> None:
        self.event_bus = event_bus or EventBus.get_instance()
        self.storage = storage or StorageBackend.get_instance()
        self.engine = DeduplicationEngine(storage=self.storage)
        
        self.event_bus.subscribe("raw_post.stored", self._on_raw_post_stored)
        logger.debug("DeduplicationAgent initialized and subscribed to raw_post.stored")

    def _on_raw_post_stored(self, payload: dict) -> None:
        raw_post_id = payload.get("raw_post_id")
        post = payload.get("post")
        
        if not post or not raw_post_id:
            return
            
        post.id = raw_post_id
        res = self.engine.evaluate_post(post)
        
        if res.action == "merge" and res.target_lead_id:
            self.storage.link_lead_source(
                canonical_lead_id=res.target_lead_id,
                raw_post_id=raw_post_id,
                confidence=res.confidence,
                merge_reason=res.reason,
                tier_used=res.tier,
            )
            self.event_bus.publish("lead.merged", {
                "canonical_lead_id": res.target_lead_id,
                "merged_post_id": raw_post_id,
                "confidence": res.confidence,
                "reason": res.reason,
                "action": "merged",
            })
            logger.info("Merged post #%d into canonical lead #%d (%s)", raw_post_id, res.target_lead_id, res.reason)
        else:
            self.event_bus.publish("lead.deduped.passed", {
                "raw_post_id": raw_post_id,
                "action": "created",
            })
```

- [ ] **Step 4: Run pytest to verify pass**

Run: `pytest tests/test_dedup_agent.py`
Expected: PASS

---

### Task 5: Full Test Suite Run & Integration Check

- [ ] **Step 1: Run pytest across the whole project**

Run: `pytest`
Expected: All 28 existing tests + new deduplication test suite PASS cleanly.
