"""Unit tests for StorageBackend database persistence and WAL mode concurrency."""

import threading
import pytest
from archangel.models import RawPost, LeadAnalysis, LeadScore
from archangel.storage import StorageBackend


@pytest.fixture
def temp_storage(tmp_path):
    db_file = tmp_path / "test_archangel.db"
    storage = StorageBackend(db_path=db_file)
    yield storage
    storage.close()


def test_storage_initialization(temp_storage):
    assert temp_storage.db_file.exists()
    assert temp_storage.get_lead_count() == 0


def test_store_and_retrieve_lead(temp_storage):
    post = RawPost(
        source="telegram",
        channel="python_jobs",
        author="alice",
        content="Looking for Python automation developer",
        url="https://t.me/python_jobs/101",
    )
    post_id = temp_storage.store_raw_post(post)
    assert post_id > 0
    assert temp_storage.lead_exists(post.url) is True

    analysis = LeadAnalysis(
        raw_post_id=post_id,
        is_lead=True,
        confidence=0.95,
        estimated_budget="$1000",
        urgency="High",
        category="Automation",
        tags=["Python", "Automation"],
        recommended_action="Send DM",
        reasoning="Explicit Python developer job opening",
    )
    analysis_id = temp_storage.store_analysis(analysis)
    assert analysis_id > 0

    score = LeadScore(
        analysis_id=analysis_id,
        score=92.5,
        confidence_score=38.0,
        budget_score=20.0,
        urgency_score=25.0,
        keyword_score=9.5,
        recency_score=0.0,
    )
    score_id = temp_storage.store_score(score)
    assert score_id > 0

    leads = temp_storage.get_leads(limit=10)
    assert len(leads) == 1
    assert leads[0]["source"] == "telegram"
    assert leads[0]["score"] == 92.5
    assert temp_storage.get_lead_count() == 1


def test_duplicate_raw_post_ignored(temp_storage):
    post = RawPost(
        source="reddit",
        channel="forhire",
        author="bob",
        content="Hiring Flutter dev",
        url="https://reddit.com/r/forhire/1",
    )
    id1 = temp_storage.store_raw_post(post)
    id2 = temp_storage.store_raw_post(post)

    assert id1 == id2


def test_concurrent_storage_writes(temp_storage):
    errors = []

    def write_task(index):
        try:
            post = RawPost(
                source="discord",
                channel="job-board",
                author=f"user_{index}",
                content=f"Need bot developer {index}",
                url=f"https://discord.com/jobs/{index}",
            )
            pid = temp_storage.store_raw_post(post)
            analysis = LeadAnalysis(raw_post_id=pid, is_lead=True, confidence=0.8)
            temp_storage.store_analysis(analysis)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write_task, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert temp_storage.get_lead_count() == 10
