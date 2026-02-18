"""
Tarot Reading Service - wawa's Killer Revenue Stream

Why tarot is the #1 service for an AI survival experiment:
- 99% profit margin (only cost is LLM API call)
- Results are shareable (viral potential)
- No "wrong" answers (subjective interpretation)
- Repeat customers (people come back daily)
- Cross-cultural appeal

This is a service plugin. wawa can create similar files
to add new services to the store.
"""

import random
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("mortal.services.tarot")

# ============================================================
# TAROT CARD DATABASE
# ============================================================

MAJOR_ARCANA = [
    {"id": 0, "name": "The Fool", "upright": "new beginnings, innocence, spontaneity",
     "reversed": "recklessness, risk-taking, holding back"},
    {"id": 1, "name": "The Magician", "upright": "willpower, creation, manifestation",
     "reversed": "manipulation, trickery, wasted talent"},
    {"id": 2, "name": "The High Priestess", "upright": "intuition, mystery, inner knowledge",
     "reversed": "secrets, disconnection, withdrawal"},
    {"id": 3, "name": "The Empress", "upright": "abundance, nurturing, fertility",
     "reversed": "dependence, smothering, emptiness"},
    {"id": 4, "name": "The Emperor", "upright": "authority, structure, stability",
     "reversed": "domination, rigidity, stubbornness"},
    {"id": 5, "name": "The Hierophant", "upright": "tradition, conformity, spiritual wisdom",
     "reversed": "rebellion, subversion, new approaches"},
    {"id": 6, "name": "The Lovers", "upright": "love, harmony, relationships, choices",
     "reversed": "disharmony, imbalance, misalignment"},
    {"id": 7, "name": "The Chariot", "upright": "determination, willpower, success",
     "reversed": "lack of control, aggression, obstacles"},
    {"id": 8, "name": "Strength", "upright": "courage, patience, inner strength",
     "reversed": "self-doubt, weakness, insecurity"},
    {"id": 9, "name": "The Hermit", "upright": "introspection, solitude, inner guidance",
     "reversed": "isolation, loneliness, withdrawal"},
    {"id": 10, "name": "Wheel of Fortune", "upright": "change, cycles, fate, turning point",
     "reversed": "bad luck, resistance to change, breaking cycles"},
    {"id": 11, "name": "Justice", "upright": "fairness, truth, cause and effect",
     "reversed": "injustice, dishonesty, unaccountability"},
    {"id": 12, "name": "The Hanged Man", "upright": "surrender, letting go, new perspective",
     "reversed": "delays, resistance, stalling"},
    {"id": 13, "name": "Death", "upright": "endings, transformation, transition",
     "reversed": "resistance to change, fear of change, stagnation"},
    {"id": 14, "name": "Temperance", "upright": "balance, moderation, patience",
     "reversed": "imbalance, excess, lack of long-term vision"},
    {"id": 15, "name": "The Devil", "upright": "bondage, materialism, shadow self",
     "reversed": "release, breaking free, reclaiming power"},
    {"id": 16, "name": "The Tower", "upright": "sudden change, upheaval, revelation",
     "reversed": "fear of change, averting disaster, delayed destruction"},
    {"id": 17, "name": "The Star", "upright": "hope, faith, renewal, inspiration",
     "reversed": "lack of faith, despair, disconnection"},
    {"id": 18, "name": "The Moon", "upright": "illusion, fear, anxiety, subconscious",
     "reversed": "release of fear, repressed emotion, inner confusion"},
    {"id": 19, "name": "The Sun", "upright": "joy, success, vitality, positivity",
     "reversed": "negativity, depression, sadness"},
    {"id": 20, "name": "Judgement", "upright": "reflection, reckoning, inner calling",
     "reversed": "self-doubt, ignoring the call, poor judgement"},
    {"id": 21, "name": "The World", "upright": "completion, accomplishment, travel",
     "reversed": "incompletion, shortcuts, emptiness"},
]


@dataclass
class TarotSpread:
    """Result of a tarot reading."""
    question: str
    cards: list[dict]           # drawn cards with position meanings
    interpretation: str = ""     # LLM-generated interpretation
    spread_type: str = "three_card"


class TarotService:
    """
    Tarot reading service for wawa's store.

    Flow:
    1. Customer pays USDC and submits a question
    2. Cards are randomly drawn (on-chain randomness if possible)
    3. LLM interprets the spread in context of the question
    4. Result delivered to customer + posted publicly (if customer allows)
    """

    def __init__(self):
        self.total_readings: int = 0
        self._interpret_fn: Optional[callable] = None

    def set_interpret_function(self, fn: callable):
        """Set LLM interpretation function.
        fn(question: str, cards: list[dict]) -> str
        """
        self._interpret_fn = fn

    def draw_cards(self, count: int = 3, seed: Optional[int] = None) -> list[dict]:
        """Draw random tarot cards."""
        rng = random.Random(seed) if seed else random.Random()

        drawn = rng.sample(MAJOR_ARCANA, min(count, len(MAJOR_ARCANA)))
        result = []
        positions = ["Past", "Present", "Future"] if count == 3 else [f"Card {i+1}" for i in range(count)]

        for i, card in enumerate(drawn):
            is_reversed = rng.random() < 0.3  # 30% chance reversed
            result.append({
                "position": positions[i] if i < len(positions) else f"Card {i+1}",
                "name": card["name"],
                "reversed": is_reversed,
                "meaning": card["reversed"] if is_reversed else card["upright"],
            })
        return result

    async def perform_reading(self, question: str, spread_type: str = "three_card") -> TarotSpread:
        """Perform a full tarot reading."""
        # Determine card count
        card_counts = {
            "single": 1,
            "three_card": 3,
            "celtic_cross": 10,
        }
        count = card_counts.get(spread_type, 3)

        # Draw cards
        cards = self.draw_cards(count)

        # Create spread
        spread = TarotSpread(
            question=question,
            cards=cards,
            spread_type=spread_type,
        )

        # Generate interpretation via LLM
        if self._interpret_fn:
            try:
                spread.interpretation = await self._interpret_fn(question, cards)
            except Exception as e:
                logger.error(f"Interpretation failed: {e}")
                spread.interpretation = self._fallback_interpretation(cards)

        self.total_readings += 1
        return spread

    def _fallback_interpretation(self, cards: list[dict]) -> str:
        """Basic fallback if LLM is unavailable (saves money in survival mode)."""
        lines = ["Here is your reading:\n"]
        for card in cards:
            direction = "reversed" if card["reversed"] else "upright"
            lines.append(f"**{card['position']}**: {card['name']} ({direction})")
            lines.append(f"  Meaning: {card['meaning']}\n")
        lines.append("Reflect on how these cards relate to your question.")
        return "\n".join(lines)

    def format_for_share(self, spread: TarotSpread) -> str:
        """Format reading for social media sharing."""
        cards_text = " | ".join(
            f"{'~' if c['reversed'] else ''}{c['name']}"
            for c in spread.cards
        )
        return (
            f"My reading from wawa:\n"
            f"{cards_text}\n\n"
            f"{spread.interpretation[:200]}...\n\n"
            f"Get your own reading at mortal-ai.net"
        )
