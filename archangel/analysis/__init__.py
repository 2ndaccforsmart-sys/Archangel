"""AI reasoning logic — converts raw posts into structured understanding."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from archangel.models import LeadAnalysis, RawPost

logger = logging.getLogger(__name__)


class IntelligenceAgent:
    """The reasoning engine. Analyses raw posts for lead potential."""

    def __init__(self) -> None:
        self._llm = None
        logger.debug("IntelligenceAgent created")

    @property
    def llm(self):
        if self._llm is None:
            try:
                from archangel.agents.chat import LLMClient
                self._llm = LLMClient()
            except Exception as exc:
                logger.warning("Could not initialize LLMClient: %s", exc)
                self._llm = None
        return self._llm

    @llm.setter
    def llm(self, value):
        self._llm = value

    def analyze(self, post: RawPost) -> LeadAnalysis:
        prompt = f"""Analyze this post and determine if it's a potential lead for software development services.

Post source: {post.source}
Author: {post.author}
Content: {post.content[:1500]}
URL: {post.url}

Determine:
1. Is this a lead? (person seeking help/developer, NOT offering services)
2. Confidence (0.0 - 1.0)
3. Estimated budget (if mentioned, or "Unknown")
4. Urgency (High/Medium/Low)
5. Category (Automation, Web Dev, Mobile, AI, Backend, Frontend, Other)
6. Tags (relevant technologies/skills)
7. Recommended action (what to do next)
8. Brief reasoning

Return ONLY valid JSON:
{{
    "is_lead": true/false,
    "confidence": 0.0-1.0,
    "estimated_budget": "...",
    "urgency": "High/Medium/Low",
    "category": "...",
    "tags": ["..."],
    "recommended_action": "...",
    "reasoning": "..."
}}"""
        try:
            if not self.llm:
                return LeadAnalysis(is_lead=False, confidence=0.0, reasoning="LLM client not available")
            response = self.llm.chat([{"role": "user", "content": prompt}])
            result = self._parse_response(response)
            return LeadAnalysis(
                raw_post_id=0,
                is_lead=result.get("is_lead", False),
                confidence=float(result.get("confidence", 0.0)),
                estimated_budget=result.get("estimated_budget", "Unknown"),
                urgency=result.get("urgency", "Medium"),
                category=result.get("category", "Other"),
                tags=result.get("tags", []),
                recommended_action=result.get("recommended_action", ""),
                reasoning=result.get("reasoning", ""),
            )
        except Exception as exc:
            logger.error("IntelligenceAgent.analyze failed for %s: %s", post.url, exc)
            return LeadAnalysis(
                is_lead=False,
                confidence=0.0,
                reasoning=f"Analysis error: {exc}",
            )

    def analyze_batch(self, posts: List[RawPost], max_workers: int = 5) -> List[Tuple[RawPost, LeadAnalysis]]:
        """Analyze a list of posts concurrently using a worker pool."""
        if not posts:
            return []

        results: List[Tuple[RawPost, LeadAnalysis]] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(posts)), thread_name_prefix="intelligence-worker") as executor:
            future_to_post = {executor.submit(self.analyze, post): post for post in posts}
            for future in as_completed(future_to_post):
                post = future_to_post[future]
                try:
                    analysis = future.result()
                    results.append((post, analysis))
                except Exception as exc:
                    logger.error("Batch analysis task failed for %s: %s", post.url, exc)
                    results.append((post, LeadAnalysis(is_lead=False, confidence=0.0, reasoning=str(exc))))

        return results

    def _parse_response(self, response: str) -> dict:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("Could not parse LLM response as JSON: %.200s", response)
        return {}
