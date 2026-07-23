"""Unit tests for IntelligenceAgent reasoning and analyze_batch parallel processing."""

from unittest.mock import MagicMock
import pytest
from archangel.analysis import IntelligenceAgent
from archangel.models import RawPost


@pytest.fixture
def mock_intelligence(monkeypatch):
    agent = IntelligenceAgent()
    mock_llm = MagicMock()
    mock_llm.chat.return_value = """{
        "is_lead": true,
        "confidence": 0.9,
        "estimated_budget": "$500-$1000",
        "urgency": "High",
        "category": "Automation",
        "tags": ["Python"],
        "recommended_action": "Reach out",
        "reasoning": "Explicit job request"
    }"""
    agent.llm = mock_llm
    return agent


def test_analyze_single_post(mock_intelligence):
    post = RawPost(
        source="telegram",
        channel="jobs",
        author="dev",
        content="Looking for Python automation engineer",
        url="https://t.me/jobs/1",
    )
    analysis = mock_intelligence.analyze(post)
    assert analysis.is_lead is True
    assert analysis.confidence == 0.9
    assert analysis.category == "Automation"


def test_analyze_batch_parallel(mock_intelligence):
    posts = [
        RawPost(source="telegram", channel="jobs", author="u1", content=f"Post content {i}", url=f"https://t.me/jobs/{i}")
        for i in range(5)
    ]
    results = mock_intelligence.analyze_batch(posts, max_workers=3)
    assert len(results) == 5
    for post, analysis in results:
        assert analysis.is_lead is True
        assert analysis.confidence == 0.9


def test_json_parse_fallback():
    agent = IntelligenceAgent()
    parsed = agent._parse_response("Sorry, I cannot help with this text.")
    assert parsed == {}


def test_json_parse_markdown_fence():
    agent = IntelligenceAgent()
    response_with_fence = """Here is your JSON response:
```json
{
    "is_lead": true,
    "confidence": 0.95
}
```
    """
    parsed = agent._parse_response(response_with_fence)
    assert parsed.get("is_lead") is True
    assert parsed.get("confidence") == 0.95

