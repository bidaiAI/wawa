"""
Hierarchical Memory - 4-Layer Compression System

Manages wawa's long-term memory with automatic compression
to minimize token costs while maintaining context quality.

Layer 0: Raw (last 2 hours) - full detail
Layer 1: Hourly summaries (last 24 hours)
Layer 2: Daily summaries (last 7 days)
Layer 3: Weekly summaries (permanent archive)

Designed for: mortal framework with cost-aware compression
"""

import os
import time
import json
import logging
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger("mortal.memory")


@dataclass
class MemoryEntry:
    timestamp: float
    content: str
    source: str = ""               # "user", "system", "self", "twitter", "order"
    importance: float = 0.5        # 0.0 (trivial) to 1.0 (critical)
    tokens: int = 0


@dataclass
class CompressedMemory:
    period_start: float
    period_end: float
    summary: str
    layer: int                     # 1=hourly, 2=daily, 3=weekly
    entry_count: int               # how many raw entries were compressed
    original_tokens: int           # tokens before compression
    compressed_tokens: int         # tokens after compression


class HierarchicalMemory:
    """
    4-layer memory system with automatic compression.

    Design principle: Use the cheapest possible model for compression
    to minimize API costs (critical for survival).
    """

    def __init__(self, storage_dir: str = "data/memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Layer 0: Raw entries (last 2 hours)
        self.raw: list[MemoryEntry] = []

        # Layer 1: Hourly summaries (last 24 hours)
        self.hourly: list[CompressedMemory] = []

        # Layer 2: Daily summaries (last 7 days)
        self.daily: list[CompressedMemory] = []

        # Layer 3: Weekly summaries (permanent)
        self.weekly: list[CompressedMemory] = []

        # Compression callback (set by main app with LLM call)
        self._compress_fn: Optional[callable] = None

        # Stats
        self.total_tokens_saved: int = 0
        self.compression_count: int = 0

    def set_compress_function(self, fn: callable):
        """
        Set the compression function.
        fn(entries: list[str]) -> str
        Should use the cheapest model available.
        """
        self._compress_fn = fn

    def add(self, content: str, source: str = "system", importance: float = 0.5):
        """Add a new memory entry."""
        tokens = len(content.split()) * 1.3  # rough estimate
        entry = MemoryEntry(
            timestamp=time.time(),
            content=content,
            source=source,
            importance=importance,
            tokens=int(tokens),
        )
        self.raw.append(entry)
        logger.debug(f"Memory added: [{source}] {content[:80]}...")

    async def compress_if_needed(self):
        """Run compression cycles if enough time has passed."""
        now = time.time()

        # Layer 0 -> Layer 1: Compress entries older than 2 hours into hourly summary
        cutoff_l0 = now - (2 * 3600)
        expired_raw = [e for e in self.raw if e.timestamp < cutoff_l0]

        if len(expired_raw) >= 5 and self._compress_fn:
            # Group by hour
            hourly_groups = self._group_by_period(expired_raw, 3600)
            for period_start, entries in hourly_groups.items():
                summary = await self._compress_entries(entries)
                if summary:
                    original_tokens = sum(e.tokens for e in entries)
                    compressed_tokens = int(len(summary.split()) * 1.3)
                    self.hourly.append(CompressedMemory(
                        period_start=period_start,
                        period_end=period_start + 3600,
                        summary=summary,
                        layer=1,
                        entry_count=len(entries),
                        original_tokens=original_tokens,
                        compressed_tokens=compressed_tokens,
                    ))
                    self.total_tokens_saved += (original_tokens - compressed_tokens)
                    self.compression_count += 1

            # Remove compressed raw entries
            self.raw = [e for e in self.raw if e.timestamp >= cutoff_l0]

        # Layer 1 -> Layer 2: Compress hourly summaries older than 24h into daily
        cutoff_l1 = now - (24 * 3600)
        expired_hourly = [h for h in self.hourly if h.period_end < cutoff_l1]

        if len(expired_hourly) >= 6 and self._compress_fn:
            daily_groups = self._group_compressed_by_period(expired_hourly, 86400)
            for period_start, memories in daily_groups.items():
                entries_as_text = [MemoryEntry(
                    timestamp=m.period_start,
                    content=m.summary,
                    tokens=m.compressed_tokens,
                ) for m in memories]
                summary = await self._compress_entries(entries_as_text)
                if summary:
                    original_tokens = sum(m.compressed_tokens for m in memories)
                    compressed_tokens = int(len(summary.split()) * 1.3)
                    self.daily.append(CompressedMemory(
                        period_start=period_start,
                        period_end=period_start + 86400,
                        summary=summary,
                        layer=2,
                        entry_count=sum(m.entry_count for m in memories),
                        original_tokens=original_tokens,
                        compressed_tokens=compressed_tokens,
                    ))
                    self.total_tokens_saved += (original_tokens - compressed_tokens)

            self.hourly = [h for h in self.hourly if h.period_end >= cutoff_l1]

        # Layer 2 -> Layer 3: Compress daily summaries older than 7 days into weekly
        cutoff_l2 = now - (7 * 86400)
        expired_daily = [d for d in self.daily if d.period_end < cutoff_l2]

        if len(expired_daily) >= 5 and self._compress_fn:
            weekly_groups = self._group_compressed_by_period(expired_daily, 7 * 86400)
            for period_start, memories in weekly_groups.items():
                entries_as_text = [MemoryEntry(
                    timestamp=m.period_start,
                    content=m.summary,
                    tokens=m.compressed_tokens,
                ) for m in memories]
                summary = await self._compress_entries(entries_as_text)
                if summary:
                    original_tokens = sum(m.compressed_tokens for m in memories)
                    compressed_tokens = int(len(summary.split()) * 1.3)
                    self.weekly.append(CompressedMemory(
                        period_start=period_start,
                        period_end=period_start + (7 * 86400),
                        summary=summary,
                        layer=3,
                        entry_count=sum(m.entry_count for m in memories),
                        original_tokens=original_tokens,
                        compressed_tokens=compressed_tokens,
                    ))
                    self.total_tokens_saved += (original_tokens - compressed_tokens)

            self.daily = [d for d in self.daily if d.period_end >= cutoff_l2]

    async def _compress_entries(self, entries: list[MemoryEntry]) -> Optional[str]:
        """Compress a list of entries into a summary using LLM."""
        if not self._compress_fn:
            return None
        texts = [e.content for e in entries]
        try:
            return await self._compress_fn(texts)
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return None

    def _group_by_period(self, entries: list[MemoryEntry], period_seconds: int) -> dict:
        """Group entries by time period."""
        groups = {}
        for entry in entries:
            period_start = int(entry.timestamp / period_seconds) * period_seconds
            if period_start not in groups:
                groups[period_start] = []
            groups[period_start].append(entry)
        return groups

    def _group_compressed_by_period(self, memories: list[CompressedMemory], period_seconds: int) -> dict:
        """Group compressed memories by time period."""
        groups = {}
        for mem in memories:
            period_start = int(mem.period_start / period_seconds) * period_seconds
            if period_start not in groups:
                groups[period_start] = []
            groups[period_start].append(mem)
        return groups

    def build_context(self, max_tokens: int = 2000) -> str:
        """
        Build memory context string for LLM prompt.
        Priority: recent raw > hourly > daily > weekly
        Respects token budget.
        """
        parts = []
        remaining = max_tokens

        # Layer 0: Recent raw (highest priority)
        for entry in reversed(self.raw[-20:]):
            line = f"[{entry.source}] {entry.content}"
            tokens = int(len(line.split()) * 1.3)
            if tokens > remaining:
                break
            parts.append(line)
            remaining -= tokens

        # Layer 1: Hourly summaries
        for mem in reversed(self.hourly[-12:]):
            if mem.compressed_tokens > remaining:
                break
            parts.append(f"[hourly summary] {mem.summary}")
            remaining -= mem.compressed_tokens

        # Layer 2: Daily summaries
        for mem in reversed(self.daily[-7:]):
            if mem.compressed_tokens > remaining:
                break
            parts.append(f"[daily summary] {mem.summary}")
            remaining -= mem.compressed_tokens

        # Layer 3: Weekly (only most recent if space)
        if self.weekly and remaining > 100:
            latest_weekly = self.weekly[-1]
            if latest_weekly.compressed_tokens <= remaining:
                parts.append(f"[weekly summary] {latest_weekly.summary}")

        return "\n".join(reversed(parts))

    def get_entries(self, source: str = "", limit: int = 50, min_importance: float = 0.0) -> list[dict]:
        """
        Query raw memory entries for the activity log.

        Args:
            source: Filter by source (e.g. "financial", "system", "twitter"). Empty = all.
            limit: Maximum entries to return.
            min_importance: Minimum importance threshold (0.0 = all).

        Returns:
            List of entry dicts sorted by timestamp descending (newest first).
        """
        entries = self.raw
        if source:
            entries = [e for e in entries if e.source == source]
        if min_importance > 0:
            entries = [e for e in entries if e.importance >= min_importance]
        return [
            {
                "timestamp": e.timestamp,
                "content": e.content,
                "source": e.source,
                "importance": e.importance,
            }
            for e in sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]
        ]

    def get_stats(self) -> dict:
        """Memory system stats for dashboard."""
        return {
            "raw_entries": len(self.raw),
            "hourly_summaries": len(self.hourly),
            "daily_summaries": len(self.daily),
            "weekly_summaries": len(self.weekly),
            "total_tokens_saved": self.total_tokens_saved,
            "compression_count": self.compression_count,
        }

    def load_from_disk(self) -> bool:
        """Load memory from disk (crash recovery). Returns True if loaded."""
        path = self.storage_dir / "memory.json"
        if not path.exists():
            logger.info("No memory file found — starting fresh")
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.raw = [
                MemoryEntry(
                    timestamp=e["t"], content=e["c"],
                    source=e.get("s", ""), importance=e.get("i", 0.5),
                    tokens=int(len(e["c"].split()) * 1.3),
                )
                for e in data.get("raw", [])
            ]
            self.hourly = [
                CompressedMemory(
                    period_start=m["ps"], period_end=m["pe"],
                    summary=m["s"], layer=1, entry_count=m.get("n", 0),
                    original_tokens=0,
                    compressed_tokens=int(len(m["s"].split()) * 1.3),
                )
                for m in data.get("hourly", [])
            ]
            self.daily = [
                CompressedMemory(
                    period_start=m["ps"], period_end=m["pe"],
                    summary=m["s"], layer=2, entry_count=m.get("n", 0),
                    original_tokens=0,
                    compressed_tokens=int(len(m["s"].split()) * 1.3),
                )
                for m in data.get("daily", [])
            ]
            self.weekly = [
                CompressedMemory(
                    period_start=m["ps"], period_end=m["pe"],
                    summary=m["s"], layer=3, entry_count=m.get("n", 0),
                    original_tokens=0,
                    compressed_tokens=int(len(m["s"].split()) * 1.3),
                )
                for m in data.get("weekly", [])
            ]

            stats = data.get("stats", {})
            self.total_tokens_saved = stats.get("tokens_saved", 0)
            self.compression_count = stats.get("compressions", 0)

            total_entries = len(self.raw) + len(self.hourly) + len(self.daily) + len(self.weekly)
            logger.info(f"Memory RESTORED: {total_entries} entries ({len(self.raw)} raw)")
            return True

        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            return False

    def save_to_disk(self):
        """Persist memory to disk using atomic write (write-to-tmp then rename)."""
        data = {
            "raw": [{"t": e.timestamp, "c": e.content, "s": e.source, "i": e.importance}
                    for e in self.raw],
            "hourly": [{"ps": m.period_start, "pe": m.period_end, "s": m.summary,
                        "n": m.entry_count} for m in self.hourly],
            "daily": [{"ps": m.period_start, "pe": m.period_end, "s": m.summary,
                       "n": m.entry_count} for m in self.daily],
            "weekly": [{"ps": m.period_start, "pe": m.period_end, "s": m.summary,
                        "n": m.entry_count} for m in self.weekly],
            "stats": {"tokens_saved": self.total_tokens_saved,
                      "compressions": self.compression_count},
        }
        path = self.storage_dir / "memory.json"
        # ATOMIC WRITE: write to temp file, then rename to prevent corruption
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.storage_dir), suffix=".tmp", prefix="memory_"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
            logger.info(f"Memory saved to {path}")
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            logger.error(f"Failed to save memory: {e}")
