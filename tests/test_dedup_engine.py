from archangel.deduplication.engine import DeduplicationEngine
from archangel.models import RawPost
from archangel.storage import StorageBackend


def test_engine_tier1_auto_merge(tmp_path):
    storage = StorageBackend(db_path=tmp_path / "test.db")
    engine = DeduplicationEngine(storage=storage)

    p1 = RawPost(
        source="reddit",
        content="Need senior Python engineer for FastAPI microservices",
        url="http://reddit.com/job1",
    )
    id1 = storage.store_raw_post(p1)
    p1.id = id1

    p2 = RawPost(
        source="discord",
        content="Need senior Python engineer for FastAPI microservices",
        url="http://discord.com/job1",
    )
    id2 = storage.store_raw_post(p2)
    p2.id = id2

    res = engine.evaluate_post(p2, candidates=[p1])
    assert res.action == "merge"
    assert res.target_lead_id == id1
    assert res.tier == "tier1"
    storage.close()


def test_engine_distinct_lead(tmp_path):
    storage = StorageBackend(db_path=tmp_path / "test.db")
    engine = DeduplicationEngine(storage=storage)

    p1 = RawPost(source="reddit", content="Need React dev", url="http://reddit.com/react")
    p1.id = storage.store_raw_post(p1)

    p2 = RawPost(
        source="github",
        content="Hiring Rust developer for WebAssembly compiler",
        url="http://github.com/rust",
    )
    p2.id = storage.store_raw_post(p2)

    res = engine.evaluate_post(p2, candidates=[p1])
    assert res.action == "create"
    assert res.target_lead_id is None
    storage.close()


def test_engine_tier2_llm_verifier(tmp_path):
    storage = StorageBackend(db_path=tmp_path / "test.db")

    # Mock verifier that approves grey zone match
    def mock_llm_verifier(p1, p2):
        return True

    engine = DeduplicationEngine(storage=storage, llm_verifier=mock_llm_verifier)

    # Moderate similarity post (grey zone 0.50 - 0.88)
    p1 = RawPost(
        source="reddit",
        content="Need senior Python backend developer for FastAPI microservices project",
        url="http://reddit.com/fastapi",
    )
    p1.id = storage.store_raw_post(p1)

    p2 = RawPost(
        source="telegram",
        content="Hiring senior Python backend engineer for FastAPI microservices architecture",
        url="http://t.me/fastapi",
    )
    p2.id = storage.store_raw_post(p2)

    res = engine.evaluate_post(p2, candidates=[p1])
    assert res.action == "merge"
    assert res.target_lead_id == p1.id
    assert res.tier == "tier2"
    storage.close()
