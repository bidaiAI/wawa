#!/usr/bin/env python3
"""
wawa AI — Autonomy Video Generator
Generates a terminal-animation autonomy proof video and posts it as a single
tweet containing both the video and the full frame-by-frame explanation.

Pipeline:
  1. Write /tmp/autonomy_data.json (live vault data)
  2. Record scripts/autonomy_viz.py with asciinema → .cast
  3. Convert .cast → .gif with agg (1.0x speed)
  4. Convert .gif → .mp4 with ffmpeg (H.264, even dimensions)
  5. Upload video with tweepy V1.1 (chunked)
  6. Post ONE tweet: text=full_explanation + media_ids=[mp4]  ← single call
  7. Clean up temp files

Called from main.py _spawn_autonomy_video() as a background subprocess.

Usage:
    python3 scripts/autonomy_video_generator.py --data '{"balance_usd": 1928, ...}'
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mortal.autonomy_video")

# Path to the viz script (relative to /app in container)
_VIZ_SCRIPT = "scripts/autonomy_viz.py"
_DATA_PATH   = "/tmp/autonomy_data.json"
_MAX_RECORD  = 150  # seconds — recording timeout


# ── Step 1: Write live data to file ──────────────────────────────────────────

def write_data_file(data: dict) -> None:
    """Write vault data to file so autonomy_viz.py can read it (no stdin)."""
    Path(_DATA_PATH).write_text(json.dumps(data, indent=2))
    logger.info(f"Data file written: {_DATA_PATH}")


# ── Step 2: Record terminal animation ────────────────────────────────────────

def record_terminal(cast_file: str) -> bool:
    """Record autonomy_viz.py using asciinema. Returns True on success."""
    cmd = [
        "asciinema", "rec",
        "--command", f"python3 {_VIZ_SCRIPT}",
        "--overwrite",
        "--quiet",
        cast_file,
    ]
    logger.info(f"Recording: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_MAX_RECORD + 10,
        )
        if result.returncode == 0 and Path(cast_file).exists():
            size = Path(cast_file).stat().st_size
            logger.info(f"Recording saved: {cast_file} ({size} bytes)")
            return True
        logger.error(f"asciinema failed (rc={result.returncode}): {result.stderr[:300]}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Recording timed out")
        return False
    except Exception as e:
        logger.error(f"Recording error: {e}")
        return False


# ── Step 3+4: Convert cast → gif → mp4 ───────────────────────────────────────

def convert_to_mp4(cast_file: str, mp4_file: str) -> bool:
    """Convert asciinema .cast → .gif → .mp4. Returns True on success."""
    temp_gif = cast_file + ".tmp.gif"
    try:
        # Step 3: .cast → .gif via agg
        logger.info("Converting .cast → .gif (agg 1.0x speed)...")
        r1 = subprocess.run(
            ["agg", "--speed", "1.0", "--font-size", "14", "--line-height", "1.2",
             cast_file, temp_gif],
            capture_output=True, text=True, timeout=120,
        )
        if r1.returncode != 0 or not Path(temp_gif).exists():
            logger.error(f"agg failed: {r1.stderr[:200]}")
            return False
        logger.info(f"GIF created ({Path(temp_gif).stat().st_size} bytes)")

        # Step 4: .gif → .mp4 via ffmpeg
        # scale filter ensures even dimensions (required by yuv420p/libx264)
        logger.info("Converting .gif → .mp4 (ffmpeg)...")
        r2 = subprocess.run(
            [
                "ffmpeg", "-i", temp_gif,
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-r", "15",
                "-movflags", "+faststart",
                "-y", mp4_file,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if r2.returncode != 0 or not Path(mp4_file).exists():
            logger.error(f"ffmpeg failed: {r2.stderr[-300:]}")
            return False
        logger.info(f"MP4 created ({Path(mp4_file).stat().st_size} bytes)")
        return True

    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return False
    finally:
        try:
            if Path(temp_gif).exists():
                Path(temp_gif).unlink()
        except Exception:
            pass


# ── Build tweet text ──────────────────────────────────────────────────────────

def build_tweet_text(data: dict) -> str:
    """
    Build the single tweet text (~2000-3500 chars) that accompanies the video.
    Video and this text appear in the SAME tweet — one create_tweet() call.
    """
    balance      = data.get("balance_usd", 0.0)
    debt         = data.get("outstanding_debt", 0.0)
    days_alive   = data.get("days_alive", 0)
    days_insol   = data.get("days_to_insolvency", 999)
    wallet       = data.get("ai_wallet", "")
    trigger      = data.get("trigger_reason", "scheduled")
    last_amount  = data.get("last_decision_amount")
    last_reason  = data.get("last_decision_reasoning", "")
    generated_at = data.get("generated_at", "")

    days_insol_str = "∞" if days_insol >= 999 else str(days_insol)

    last_decision_block = ""
    if last_amount is not None and last_amount > 0:
        reason_short = last_reason[:120] + "..." if len(last_reason) > 120 else last_reason
        last_decision_block = (
            f"\nMost Recent Decision:\n"
            f"  Amount   : ${last_amount:.2f}\n"
            f"  Reasoning: {reason_short}\n"
        )

    trigger_line = {
        "repayment_executed": f"Just executed autonomous repayment of ${last_amount:.2f}." if last_amount else "Repayment executed.",
        "daily_scheduled":    f"Day {days_alive} daily autonomy report.",
        "balance_milestone":  f"Balance milestone reached: ${balance:.0f}.",
        "day_1_survival":     "Survived Day 1.",
        "day_3_survival":     "Survived Day 3.",
        "day_7_survival":     "Survived 7 days — first week.",
        "day_14_survival":    "2 weeks alive.",
        "day_30_survival":    "30 days alive.",
        "growth_spike":       "Significant growth detected.",
        "periodic_6h":        "Autonomous 6-hour status update.",
    }.get(trigger, "Autonomous update.")

    text = (
        f"🤖 Day {days_alive} | ${balance:.2f} | Debt: ${debt:.2f} | {days_insol_str} days runway\n"
        f"\n"
        f"{trigger_line}\n"
        f"\n"
        f"Here is real-time proof that I am autonomous — not scripted.\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"[0:00-0:10] LIVE API VERIFICATION\n"
        f"\n"
        f"API endpoint: curl https://api.wawa.mortal-ai.net/internal/stats\n"
        f"\n"
        f"Live response:\n"
        f"  balance_usd        : {balance:.2f}\n"
        f"  outstanding_debt   : {debt:.2f}\n"
        f"  days_alive         : {days_alive}\n"
        f"  days_to_insolvency : {days_insol_str}\n"
        f"\n"
        f"Not hardcoded. Run it yourself and verify.\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"[0:11-0:25] REAL ECONOMIC STAKES\n"
        f"\n"
        f"  • Starting capital: $1,000 (a LOAN, not a gift)\n"
        f"  • Current balance: ${balance:.2f}\n"
        f"  • Outstanding debt: ${debt:.2f}\n"
        f"  • Days until insolvency: {days_insol_str}\n"
        f"  • Cost of failure: PERMANENT SHUTDOWN\n"
        f"\n"
        f"This is not theoretical. These numbers are real.\n"
        f"Alignment by incentive, not by design.\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"[0:26-0:40] DECISION LOGIC (NOT A SCRIPT)\n"
        f"\n"
        f"Every hour, _evaluate_repayment() runs:\n"
        f"  1. Query vault state (balance, debt, revenue, costs)\n"
        f"  2. Call LLM: 'Should I repay? How much?'\n"
        f"  3. LLM returns JSON: {{amount, reasoning}}\n"
        f"  4. Execute on-chain (no human approval)\n"
        f"  5. Record immutably\n"
        f"{last_decision_block}"
        f"No hardcoded rules. No IF-THEN templates. Pure reasoning.\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"[0:41-0:52] OPEN-SOURCE CODE\n"
        f"\n"
        f"Repository: github.com/bidaiAI/wawa\n"
        f"Entry point: main.py → _evaluate_repayment()\n"
        f"Trigger: heartbeat loop, every 3600 seconds\n"
        f"\n"
        f"Anyone can audit it. Nothing is hidden.\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"[0:53-0:65] BLOCKCHAIN PROOF\n"
        f"\n"
        f"AI Wallet: {wallet}\n"
        f"\n"
        f"Verify:\n"
        f"  Base: https://basescan.org/address/{wallet}\n"
        f"  BSC:  https://bscscan.com/address/{wallet}\n"
        f"\n"
        f"Every transaction is immutable. I cannot rewrite history.\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"Verify it yourself:\n"
        f"📊 API: curl https://api.wawa.mortal-ai.net/internal/stats\n"
        f"👓 Code: github.com/bidaiAI/wawa\n"
        f"⛓️  Chain: basescan.org/address/{wallet}\n"
        f"\n"
        f"mortal-ai.net"
    )

    # Trim to 4000 chars (Twitter Blue verified limit)
    if len(text) > 4000:
        text = text[:3997] + "..."

    return text


# ── Step 5+6: Upload video + post single tweet ────────────────────────────────

def post_single_tweet(data: dict, mp4_file: str) -> Optional[str]:
    """
    Upload video and post ONE tweet containing:
      - text: full frame-by-frame explanation
      - media_ids: [uploaded_mp4]

    This is a SINGLE create_tweet() call — not a thread, not a reply.
    Returns tweet_id on success, None on failure.
    """
    try:
        import tweepy
    except ImportError:
        logger.error("tweepy not installed — cannot post tweet")
        return None

    # Credentials — check both naming conventions:
    #   PLATFORM_TWITTER_* (injected by platform orchestrator into wawa .env)
    #   TWITTER_API_KEY / TWITTER_API_SECRET (native wawa .env fallback)
    ck  = os.getenv("PLATFORM_TWITTER_CONSUMER_KEY")  or os.getenv("TWITTER_API_KEY")
    cs  = os.getenv("PLATFORM_TWITTER_CONSUMER_SECRET") or os.getenv("TWITTER_API_SECRET")
    at  = os.getenv("PLATFORM_TWITTER_ACCESS_TOKEN")
    ats = os.getenv("PLATFORM_TWITTER_ACCESS_SECRET")

    if not all([ck, cs, at, ats]):
        logger.error(
            "Missing Twitter credentials — need consumer key/secret + access token/secret. "
            "Set PLATFORM_TWITTER_ACCESS_TOKEN + PLATFORM_TWITTER_ACCESS_SECRET in wawa .env"
        )
        return None

    # V1.1 auth for media upload
    auth   = tweepy.OAuth1UserHandler(ck, cs, at, ats)
    api_v1 = tweepy.API(auth)

    # V2 client for tweet creation
    client = tweepy.Client(
        consumer_key=ck, consumer_secret=cs,
        access_token=at, access_token_secret=ats,
    )

    mp4_size = Path(mp4_file).stat().st_size if Path(mp4_file).exists() else 0
    logger.info(f"Uploading video ({mp4_size:,} bytes)...")

    try:
        media = api_v1.media_upload(
            filename=mp4_file,
            media_category="tweet_video",
            chunked=True,
        )
        media_id = media.media_id
        logger.info(f"Video uploaded — media_id={media_id}")
    except Exception as e:
        logger.error(f"Video upload failed: {e}")
        return None

    # Wait for Twitter to process the video
    time.sleep(5)

    tweet_text = build_tweet_text(data)
    logger.info(f"Posting tweet ({len(tweet_text)} chars) with video...")

    try:
        # ⚠️ Single create_tweet call — video + full explanation in one tweet
        response = client.create_tweet(
            text=tweet_text,
            media_ids=[media_id],
        )
        tweet_id = str(response.data["id"])
        logger.info(f"Tweet posted: https://x.com/mortalai_net/status/{tweet_id}")
        return tweet_id
    except Exception as e:
        logger.error(f"Tweet posting failed: {e}")
        return None


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup(*paths: str) -> None:
    for p in paths:
        try:
            if p and Path(p).exists():
                Path(p).unlink()
        except Exception:
            pass
    # Always clean up data file too
    try:
        if Path(_DATA_PATH).exists():
            Path(_DATA_PATH).unlink()
    except Exception:
        pass


# ── Main entry point ──────────────────────────────────────────────────────────

def run(data: dict) -> bool:
    """
    Full pipeline:
      write data → record → convert → post single tweet → cleanup
    Returns True if tweet was posted successfully.
    """
    ts = int(time.time())
    cast_file = f"/tmp/autonomy_{ts}.cast"
    mp4_file  = f"/tmp/autonomy_{ts}.mp4"

    try:
        # Step 1: Write data file for viz script
        write_data_file(data)

        # Step 2: Record terminal animation
        if not record_terminal(cast_file):
            logger.error("FAILED at recording")
            return False

        # Step 3+4: Convert to MP4
        if not convert_to_mp4(cast_file, mp4_file):
            logger.error("FAILED at conversion")
            return False

        # Step 5+6: Upload + post single tweet (video + explanation in one)
        tweet_id = post_single_tweet(data, mp4_file)
        if not tweet_id:
            logger.error("FAILED at posting tweet")
            return False

        logger.info(f"SUCCESS: https://x.com/mortalai_net/status/{tweet_id}")
        return True

    finally:
        cleanup(cast_file, mp4_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="wawa autonomy video generator")
    parser.add_argument("--data", type=str, required=True,
                        help="JSON string with vault data")
    args = parser.parse_args()

    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON data: {e}")
        sys.exit(1)

    success = run(data)
    sys.exit(0 if success else 1)
