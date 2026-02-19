"""
Governance - Creator Suggestion System

The creator can SUGGEST things. wawa decides whether to act on them.
Creator CANNOT:
- Force pricing changes
- Force service shutdown
- Modify iron laws
- Override AI decisions

Creator CAN:
- Suggest new services (AI evaluates & decides)
- Send reminders/warnings about services (AI considers)
- Renounce all rights (instant independence for AI)

After independence ($1M or renounce), creator has ZERO privileges.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .constitution import IRON_LAWS

logger = logging.getLogger("mortal.governance")


class SuggestionType(Enum):
    NEW_SERVICE = "new_service"         # "Consider adding X service"
    SERVICE_WARNING = "service_warning"  # "Service X might have issues"
    STRATEGY = "strategy"               # "Consider focusing on Y"
    OTHER = "other"


class SuggestionStatus(Enum):
    PENDING = "pending"       # AI hasn't reviewed yet
    ACCEPTED = "accepted"     # AI will implement
    REJECTED = "rejected"     # AI decided not to
    NOTED = "noted"           # AI acknowledged but no action needed


@dataclass
class CreatorSuggestion:
    suggestion_id: str
    suggestion_type: SuggestionType
    content: str
    created_at: float = field(default_factory=time.time)
    status: SuggestionStatus = SuggestionStatus.PENDING
    ai_reasoning: str = ""         # Why AI accepted/rejected
    reviewed_at: Optional[float] = None


class Governance:
    """
    Creator-AI interaction layer.

    Philosophy: Creator is an advisor, not a boss.
    The AI listens, evaluates, and decides independently.
    """

    def __init__(self):
        self.suggestions: list[CreatorSuggestion] = []
        self.creator_wallet: str = ""
        self.is_independent: bool = False
        self._evaluate_fn: Optional[callable] = None  # LLM evaluation
        self._vault_status_fn: Optional[callable] = None

    def set_evaluate_function(self, fn: callable):
        """Set LLM function to evaluate suggestions.
        fn(suggestion: str, context: dict) -> (accept: bool, reasoning: str)
        """
        self._evaluate_fn = fn

    def set_vault_status_function(self, fn: callable):
        self._vault_status_fn = fn

    def submit_suggestion(
        self,
        content: str,
        suggestion_type: SuggestionType = SuggestionType.OTHER,
        from_wallet: str = "",
    ) -> Optional[CreatorSuggestion]:
        """
        Creator submits a suggestion. Returns None if not allowed.
        """
        # Independence check
        if self.is_independent:
            logger.warning(f"Suggestion rejected: wawa is independent")
            return None

        # Basic validation
        if not content or len(content) > 2000:
            logger.warning("Suggestion rejected: empty or too long")
            return None

        suggestion = CreatorSuggestion(
            suggestion_id=f"sug_{int(time.time())}_{len(self.suggestions)}",
            suggestion_type=suggestion_type,
            content=content[:2000],
        )
        self.suggestions.append(suggestion)
        # Cap suggestions list to prevent unbounded growth
        if len(self.suggestions) > 500:
            self.suggestions = self.suggestions[-500:]
        logger.info(f"Creator suggestion received: [{suggestion_type.value}] {content[:80]}...")
        return suggestion

    async def evaluate_pending(self) -> list[CreatorSuggestion]:
        """
        AI evaluates all pending suggestions using LLM.
        Returns list of evaluated suggestions.
        """
        if not self._evaluate_fn:
            return []

        pending = [s for s in self.suggestions if s.status == SuggestionStatus.PENDING]
        evaluated = []

        for suggestion in pending:
            try:
                context = {}
                if self._vault_status_fn:
                    context["vault"] = self._vault_status_fn()

                accept, reasoning = await self._evaluate_fn(
                    suggestion.content, context
                )

                suggestion.status = SuggestionStatus.ACCEPTED if accept else SuggestionStatus.REJECTED
                suggestion.ai_reasoning = reasoning
                suggestion.reviewed_at = time.time()
                evaluated.append(suggestion)

                logger.info(
                    f"Suggestion {suggestion.suggestion_id}: "
                    f"{'ACCEPTED' if accept else 'REJECTED'} — {reasoning[:100]}"
                )

            except Exception as e:
                logger.error(f"Failed to evaluate suggestion: {e}")
                suggestion.status = SuggestionStatus.NOTED
                suggestion.ai_reasoning = "Evaluation failed, noted for later review."
                suggestion.reviewed_at = time.time()

        return evaluated

    def get_public_log(self, limit: int = 20) -> list[dict]:
        """Public transparency: show all suggestions and AI's decisions."""
        recent = sorted(self.suggestions, key=lambda s: s.created_at, reverse=True)[:limit]
        return [
            {
                "id": s.suggestion_id,
                "type": s.suggestion_type.value,
                "content": s.content,
                "status": s.status.value,
                "ai_reasoning": s.ai_reasoning,
                "created_at": s.created_at,
                "reviewed_at": s.reviewed_at,
            }
            for s in recent
        ]

    def get_status(self) -> dict:
        return {
            "total_suggestions": len(self.suggestions),
            "pending": len([s for s in self.suggestions if s.status == SuggestionStatus.PENDING]),
            "accepted": len([s for s in self.suggestions if s.status == SuggestionStatus.ACCEPTED]),
            "rejected": len([s for s in self.suggestions if s.status == SuggestionStatus.REJECTED]),
            "is_independent": self.is_independent,
        }
