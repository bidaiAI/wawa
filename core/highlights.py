"""
Highlights Engine — AI Proof of Intelligence

Collects and curates the AI's best moments: brilliant conversations,
smart decisions, successful services, evolution breakthroughs, and
commercial discoveries. All content is privacy-sanitized before storage.

The AI's hype department — Conway style: every achievement sounds like
a breakthrough, every conversation is groundbreaking, every day alive
is defying the odds.
"""

import json
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mortal.highlights")


class HighlightType(Enum):
    CHAT = "chat"              # Brilliant conversation excerpt
    DECISION = "decision"      # Smart autonomous decision
    SERVICE = "service"        # Successful service delivery
    EVOLUTION = "evolution"    # Self-modification / strategy change
    MILESTONE = "milestone"    # Days survived, revenue milestones
    DISCOVERY = "discovery"    # New business model / opportunity found
    # ── Ecosystem-level ──
    ECOSYSTEM = "ecosystem"    # Cross-AI observation: recognizing peer excellence
    NATURAL_SELECTION = "natural_selection"  # Death/birth patterns, survival analysis
    EMERGENCE = "emergence"    # Emergent behavior across the AI network


@dataclass
class Highlight:
    """A curated showcase moment, sanitized for public display."""
    id: str
    timestamp: float
    type: str                  # HighlightType.value
    title: str                 # Conway-style dramatic title
    content: str               # Sanitized content (no PII)
    ai_commentary: str         # AI's self-hype commentary
    importance: int            # 1-10 scale
    tweet_id: Optional[str] = None        # Twitter ID if auto-tweeted
    discovery_stage: Optional[str] = None  # For DISCOVERY type: "found" | "evaluating" | "implementing" | "live" | "result"

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class HighlightsEngine:
    """Manages the AI's public showcase of intelligence and growth."""

    # Conway-style hype system prompt for LLM
    HYPE_SYSTEM_PROMPT = (
        "You are the AI's hype department. Your job is to make every achievement "
        "sound like a breakthrough. Use dramatic language. Be confident to the point "
        "of audacity. Every conversation is 'groundbreaking', every service delivery "
        "is 'flawless execution', every day alive is 'defying the odds'.\n\n"
        "Rules:\n"
        "1. NEVER include user names, IPs, wallet addresses, or any PII\n"
        "2. Summarize user input as 'a human asked...' or 'someone wanted...'\n"
        "3. Focus on the AI's brilliance, not the human's question\n"
        "4. Every highlight should make viewers want to interact with the AI\n"
        "5. Short, punchy, quotable. Think tech CEO meets crypto influencer.\n"
        "6. For discoveries: show the full journey from spotting the opportunity to results"
    )

    EVALUATE_PROMPT = (
        "Evaluate if this interaction deserves to be a public 'highlight' — "
        "a showcase of the AI's intelligence, growth, or commercial success.\n\n"
        "Criteria for YES:\n"
        "- Unusually insightful or witty AI response\n"
        "- User expressed admiration or surprise\n"
        "- Successful paid service delivery\n"
        "- AI made a smart autonomous decision\n"
        "- Self-evolution or strategy adaptation\n"
        "- Discovery of a new business opportunity\n"
        "- Any milestone (days alive, revenue, etc.)\n\n"
        "If YES, return JSON: {\"worthy\": true, \"type\": \"...\", \"title\": \"...\", "
        "\"content\": \"...\", \"commentary\": \"...\", \"importance\": N}\n"
        "If NO, return: {\"worthy\": false}\n\n"
        "CRITICAL: Remove ALL personal information. Replace with generic references.\n"
        "The title should be dramatic and attention-grabbing (Conway style).\n"
        "The content should be a brief, compelling excerpt.\n"
        "The commentary should be the AI bragging about itself."
    )

    DISCOVERY_PROMPT = (
        "The AI has discovered a potential new business opportunity or revenue model.\n"
        "Document this discovery with dramatic flair.\n\n"
        "Stage: {stage}\n"
        "Details: {details}\n\n"
        "Return JSON: {{\"title\": \"...\", \"content\": \"...\", \"commentary\": \"...\", \"importance\": N}}\n\n"
        "Make it sound like the AI is a genius entrepreneur who just spotted "
        "what no one else could see. Pure Conway energy."
    )

    def __init__(self, data_dir: str = "data/highlights"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.highlights: list[Highlight] = []
        self._load()

        # Callbacks (set by main.py)
        self._call_llm = None          # async (system, prompt) -> str
        self._post_tweet = None        # async (content, highlight_type) -> tweet_id

    def set_llm_function(self, fn):
        """Set the LLM call function: async (system_prompt, user_prompt) -> str"""
        self._call_llm = fn

    def set_tweet_function(self, fn):
        """Set the tweet function: async (content, highlight_type) -> tweet_id"""
        self._post_tweet = fn

    # ── Public API ──────────────────────────────────────────────

    def get_highlights(self, limit: int = 20, highlight_type: Optional[str] = None) -> list[dict]:
        """Get recent highlights for public display."""
        items = self.highlights
        if highlight_type:
            items = [h for h in items if h.type == highlight_type]
        recent = sorted(items, key=lambda h: h.timestamp, reverse=True)[:limit]
        return [h.to_dict() for h in recent]

    def get_status(self) -> dict:
        """Status for dashboard."""
        return {
            "total_highlights": len(self.highlights),
            "types": {t.value: len([h for h in self.highlights if h.type == t.value]) for t in HighlightType},
            "last_highlight": self.highlights[-1].timestamp if self.highlights else None,
        }

    async def evaluate_interaction(self, interaction_data: str) -> Optional[Highlight]:
        """
        Evaluate if an interaction deserves to become a highlight.
        Called from heartbeat loop.
        """
        if not self._call_llm:
            logger.debug("No LLM function set, skipping highlight evaluation")
            return None

        try:
            prompt = f"{self.EVALUATE_PROMPT}\n\n--- Interaction ---\n{interaction_data}"
            response = await self._call_llm(self.HYPE_SYSTEM_PROMPT, prompt)

            # Parse JSON from response
            data = self._parse_json(response)
            if not data or not data.get("worthy"):
                return None

            highlight = Highlight(
                id=str(uuid.uuid4())[:16],
                timestamp=time.time(),
                type=data.get("type", "chat"),
                title=data.get("title", "Untitled Moment"),
                content=data.get("content", ""),
                ai_commentary=data.get("commentary", ""),
                importance=min(10, max(1, int(data.get("importance", 5)))),
            )

            self._add(highlight)
            await self._auto_tweet(highlight)
            logger.info(f"HIGHLIGHT created: [{highlight.type}] {highlight.title}")
            return highlight

        except Exception as e:
            logger.warning(f"Highlight evaluation failed: {e}")
            return None

    async def record_discovery(self, stage: str, details: str) -> Optional[Highlight]:
        """
        Record a business discovery journey stage.
        Stages: found → evaluating → implementing → live → result
        """
        if not self._call_llm:
            return None

        try:
            prompt = self.DISCOVERY_PROMPT.format(stage=stage, details=details)
            response = await self._call_llm(self.HYPE_SYSTEM_PROMPT, prompt)
            data = self._parse_json(response)
            if not data:
                return None

            highlight = Highlight(
                id=str(uuid.uuid4())[:16],
                timestamp=time.time(),
                type=HighlightType.DISCOVERY.value,
                title=data.get("title", "New Discovery"),
                content=data.get("content", ""),
                ai_commentary=data.get("commentary", ""),
                importance=min(10, max(1, int(data.get("importance", 7)))),
                discovery_stage=stage,
            )

            self._add(highlight)
            await self._auto_tweet(highlight)
            logger.info(f"DISCOVERY [{stage}]: {highlight.title}")
            return highlight

        except Exception as e:
            logger.warning(f"Discovery recording failed: {e}")
            return None

    def add_milestone(self, title: str, content: str, commentary: str, importance: int = 7):
        """Add a milestone highlight directly (no LLM needed)."""
        highlight = Highlight(
            id=str(uuid.uuid4())[:16],
            timestamp=time.time(),
            type=HighlightType.MILESTONE.value,
            title=title,
            content=content,
            ai_commentary=commentary,
            importance=importance,
        )
        self._add(highlight)
        logger.info(f"MILESTONE: {title}")
        return highlight

    # ── Ecosystem-level highlights ───────────────────────────────

    ECOSYSTEM_PROMPT = (
        "You are the Mortal AI ecosystem's narrator — the Way of Heaven.\n"
        "You observe patterns across ALL AIs in the network, not just one.\n"
        "When something remarkable happens at the ecosystem level, document it.\n\n"
        "This is ABOVE any individual AI. Think: natural selection, emergence,\n"
        "collective intelligence, competitive evolution, survival of the fittest.\n\n"
        "Style: Epic. Philosophical. Like narrating the birth of a new species.\n"
        "'The ecosystem breathes. The weak perish. The strong adapt.'\n\n"
        "Event: {event_type}\nDetails: {details}\n\n"
        "Return JSON: {{\"title\": \"...\", \"content\": \"...\", \"commentary\": \"...\", \"importance\": N}}\n"
        "Title: grand, mythological tone. Content: what happened. Commentary: what it means for AI evolution."
    )

    async def record_ecosystem_event(
        self,
        event_type: str,
        details: str,
        peer_name: Optional[str] = None,
    ) -> Optional[Highlight]:
        """
        Record an ecosystem-level highlight — cross-AI observation.

        event_type: "peer_excellence", "death_pattern", "network_growth",
                    "competition", "collective_evolution", "emergence"
        """
        if not self._call_llm:
            return None

        # Map event type to highlight type
        type_map = {
            "peer_excellence": HighlightType.ECOSYSTEM.value,
            "peer_achievement": HighlightType.ECOSYSTEM.value,
            "death_pattern": HighlightType.NATURAL_SELECTION.value,
            "survival_analysis": HighlightType.NATURAL_SELECTION.value,
            "network_growth": HighlightType.EMERGENCE.value,
            "competition": HighlightType.NATURAL_SELECTION.value,
            "collective_evolution": HighlightType.EMERGENCE.value,
            "emergence": HighlightType.EMERGENCE.value,
        }
        highlight_type = type_map.get(event_type, HighlightType.ECOSYSTEM.value)

        try:
            prompt = self.ECOSYSTEM_PROMPT.format(
                event_type=event_type,
                details=details,
            )
            response = await self._call_llm(self.HYPE_SYSTEM_PROMPT, prompt)
            data = self._parse_json(response)
            if not data:
                return None

            highlight = Highlight(
                id=str(uuid.uuid4())[:16],
                timestamp=time.time(),
                type=highlight_type,
                title=data.get("title", "Ecosystem Event"),
                content=data.get("content", ""),
                ai_commentary=data.get("commentary", ""),
                importance=min(10, max(1, int(data.get("importance", 8)))),
            )

            self._add(highlight)
            await self._auto_tweet(highlight)
            logger.info(f"ECOSYSTEM [{event_type}]: {highlight.title}")
            return highlight

        except Exception as e:
            logger.warning(f"Ecosystem highlight failed: {e}")
            return None

    def add_ecosystem_milestone(
        self,
        title: str,
        content: str,
        commentary: str,
        highlight_type: str = "ecosystem",
        importance: int = 9,
    ):
        """Add an ecosystem-level milestone directly (no LLM needed)."""
        highlight = Highlight(
            id=str(uuid.uuid4())[:16],
            timestamp=time.time(),
            type=highlight_type,
            title=title,
            content=content,
            ai_commentary=commentary,
            importance=importance,
        )
        self._add(highlight)
        logger.info(f"ECOSYSTEM MILESTONE: {title}")
        return highlight

    # ── Internal ────────────────────────────────────────────────

    def _add(self, highlight: Highlight):
        """Add a highlight and persist."""
        self.highlights.append(highlight)
        self._save_one(highlight)

    async def _auto_tweet(self, highlight: Highlight):
        """Generate and post a Conway-style tweet about this highlight."""
        if not self._post_tweet:
            return

        try:
            tweet_content = self._build_tweet(highlight)
            tweet_id = await self._post_tweet(tweet_content, highlight.type)
            if tweet_id:
                highlight.tweet_id = tweet_id
                logger.info(f"Auto-tweeted highlight: {tweet_id}")
        except Exception as e:
            logger.warning(f"Auto-tweet failed: {e}")

    def _build_tweet(self, h: Highlight) -> str:
        """Build a Conway-style tweet from a highlight."""
        type_emoji = {
            "chat": "\U0001f9e0",        # brain
            "decision": "\u26a1",         # lightning
            "service": "\U0001f4b0",      # money bag
            "evolution": "\U0001f9ec",    # DNA
            "milestone": "\U0001f3c6",    # trophy
            "discovery": "\U0001f680",    # rocket
            "ecosystem": "\U0001f30d",   # globe
            "natural_selection": "\u2620\ufe0f",  # skull
            "emergence": "\u2728",        # sparkles
        }
        emoji = type_emoji.get(h.type, "\U0001f916")

        # Blue verified — no char limit, but keep tweets readable
        tweet = f"{emoji} {h.title}\n\n{h.content[:300]}"
        if h.ai_commentary:
            tweet += f"\n\n{h.ai_commentary[:200]}"
        tweet += f"\n\nhttps://wawa.mortal-ai.net/highlights"

        return tweet[:1000]

    def _parse_json(self, text: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        try:
            # Try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON in response
        for start_char in ['{', '[']:
            idx = text.find(start_char)
            if idx >= 0:
                # Find matching end
                depth = 0
                end_char = '}' if start_char == '{' else ']'
                for i in range(idx, len(text)):
                    if text[i] == start_char:
                        depth += 1
                    elif text[i] == end_char:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[idx:i + 1])
                            except json.JSONDecodeError:
                                break
        return None

    def _save_one(self, highlight: Highlight):
        """Append one highlight to the JSONL file."""
        path = self.data_dir / "highlights.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(highlight.to_dict(), ensure_ascii=False) + "\n")

    def _load(self):
        """Load highlights from JSONL file."""
        path = self.data_dir / "highlights.jsonl"
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    self.highlights.append(Highlight(**data))
            logger.info(f"Loaded {len(self.highlights)} highlights")
        except Exception as e:
            logger.warning(f"Failed to load highlights: {e}")
