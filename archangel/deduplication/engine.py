"""Two-Tier Hybrid Deduplication Engine (Approach D)."""

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from archangel.deduplication.fingerprint import compute_post_similarity
from archangel.models import RawPost
from archangel.storage import StorageBackend

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    action: str  # "merge" or "create"
    target_lead_id: Optional[int]
    confidence: float
    reason: str
    tier: str


class DeduplicationEngine:
    """Evaluates incoming posts using Tier 1 (fast rules & similarity) and Tier 2 (LLM verification)."""

    def __init__(
        self,
        storage: Optional[StorageBackend] = None,
        llm_verifier: Optional[Callable[[RawPost, RawPost], bool]] = None,
    ) -> None:
        self.storage = storage or StorageBackend.get_instance()
        self.llm_verifier = llm_verifier

    def evaluate_post(
        self, new_post: RawPost, candidates: Optional[List[RawPost]] = None
    ) -> DeduplicationResult:
        """Evaluate a post against candidates to decide whether to merge or create a new lead."""
        if candidates is None:
            raw_leads = self.storage.get_leads(limit=100)
            candidates = []
            for r in raw_leads:
                post_id = r.get("id")
                if post_id and post_id != new_post.id:
                    p = RawPost(
                        source=r.get("source", ""),
                        channel=r.get("channel", ""),
                        author=r.get("author", ""),
                        content=r.get("content", ""),
                        url=r.get("url", ""),
                        metadata={},
                    )
                    p.id = post_id
                    candidates.append(p)

        best_candidate: Optional[RawPost] = None
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
                confidence=round(1.0 - best_sim, 4),
                reason="No candidate reached minimum similarity threshold (0.50)",
                tier="tier1",
            )

        # Tier 2 decisions (Grey area: 0.50 <= best_sim < 0.88)
        if self.llm_verifier and best_candidate:
            try:
                is_match = self.llm_verifier(new_post, best_candidate)
                if is_match:
                    return DeduplicationResult(
                        action="merge",
                        target_lead_id=best_candidate.id,
                        confidence=0.85,
                        reason=f"LLM verified match with post #{best_candidate.id}",
                        tier="tier2",
                    )
            except Exception as exc:
                logger.warning("LLM verifier failed during deduplication: %s", exc)

        return DeduplicationResult(
            action="create",
            target_lead_id=None,
            confidence=0.70,
            reason=f"Similarity in grey zone ({best_sim:.2f}) but LLM did not verify match",
            tier="tier2" if self.llm_verifier else "tier1_fallback",
        )
