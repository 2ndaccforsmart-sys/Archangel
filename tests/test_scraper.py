"""Unit tests for SmartScraper keyword heuristic loading and intent detection."""

from archangel.agents.scraper import SmartScraper


def test_smart_scraper_keyword_loading():
    scraper = SmartScraper()
    assert hasattr(scraper, "title_demand_keywords")
    assert hasattr(scraper, "supply_signals")
    assert "[hiring]" in scraper.title_demand_keywords
    assert "[for hire]" in scraper.supply_signals


def test_has_buyer_intent():
    scraper = SmartScraper()
    # Explicit hiring title
    assert scraper._has_buyer_intent("[HIRING] Need a Python developer to build a web scraper") is True
    # Supply-side title should be rejected
    assert scraper._has_buyer_intent("[FOR HIRE] Experienced Fullstack Developer available") is False
