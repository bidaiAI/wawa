#!/usr/bin/env python3
"""
Monetization Analysis Video Generator — Records terminal visualization to MP4.

Triggered when growth rate changes >10% or transitions from stagnation to growth.
Records asciinema, converts to MP4, posts to Twitter, cleans up temp files.

No private keys. All cleanup happens after tweet posting.
"""
import json
import subprocess
import sys
import time
import os
import tempfile
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_asciinema_recording(analysis_data: dict, output_cast: str, max_duration: int = 120) -> bool:
    """
    Record monetization_analysis_viz.py via asciinema.

    Args:
        analysis_data: Dict with balance, growth_pct, etc. (passed via stdin)
        output_cast: Path to save .cast file
        max_duration: Max recording time in seconds

    Returns:
        True if recording succeeded
    """
    try:
        logger.info(f"Starting asciinema recording to {output_cast}")

        # Prepare input data as JSON
        input_json = json.dumps(analysis_data)

        # Script path (works both on VPS /app and local dev E:\mortal)
        viz_script = "/app/scripts/monetization_analysis_viz.py"
        if not os.path.exists(viz_script):
            viz_script = str(Path(__file__).parent / "monetization_analysis_viz.py")

        # asciinema rec --command "python3 script.py" --overwrite output.cast
        # Data passed via stdin
        cmd = [
            "asciinema", "rec",
            "--command", f"python3 {viz_script}",
            "--overwrite",
            "--quiet",  # Minimal asciinema UI
            output_cast
        ]

        # Run with timeout, passing JSON data via stdin
        result = subprocess.run(
            cmd,
            input=input_json,
            capture_output=True,
            text=True,
            timeout=max_duration + 10
        )

        if result.returncode == 0 and os.path.exists(output_cast):
            file_size = os.path.getsize(output_cast)
            logger.info(f"✓ Recording saved: {output_cast} ({file_size} bytes)")
            return True
        else:
            logger.error(f"✗ Asciinema failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("✗ Recording timeout")
        return False
    except Exception as e:
        logger.error(f"✗ Recording error: {e}")
        return False


def convert_cast_to_mp4(cast_file: str, mp4_file: str) -> bool:
    """
    Convert asciinema .cast to MP4 using agg (asciinema-agg) → GIF → ffmpeg → MP4.

    Requires: agg installed (pip install asciinema-agg) and ffmpeg

    Process:
    1. agg: .cast → .gif (with ANSI rendering)
    2. ffmpeg: .gif → .mp4 (with compression)

    Returns:
        True if conversion succeeded
    """
    try:
        logger.info(f"Converting {cast_file} to MP4")

        gif_file = cast_file.replace(".cast", ".gif")
        temp_gif = f"{cast_file}.tmp.gif"

        # Step 1: Convert .cast to GIF using agg
        logger.info("  Step 1: Converting .cast to GIF with agg...")
        try:
            cmd_agg = [
                "agg",
                "--speed", "2.0",  # 2x speed for faster playback
                "--font-size", "14",
                "--line-height", "1.2",
                cast_file,
                temp_gif
            ]
            result_agg = subprocess.run(cmd_agg, capture_output=True, text=True, timeout=120)

            if result_agg.returncode != 0:
                logger.error(f"  agg failed: {result_agg.stderr}")
                return False

            if not os.path.exists(temp_gif):
                logger.error("  agg did not create GIF file")
                return False

            gif_size = os.path.getsize(temp_gif)
            logger.info(f"  ✓ GIF created ({gif_size} bytes)")

        except FileNotFoundError:
            logger.error("  agg not found. Install: pip install asciinema-agg")
            return False

        # Step 2: Convert GIF to MP4 using ffmpeg
        logger.info("  Step 2: Converting GIF to MP4 with ffmpeg...")
        try:
            cmd_ffmpeg = [
                "ffmpeg",
                "-i", temp_gif,
                "-c:v", "libx264",  # H.264 video codec
                "-crf", "23",  # Quality (0-51, lower=better, 23 is default)
                "-preset", "fast",  # Speed (ultrafast, superfast, veryfast, faster, fast, medium)
                "-pix_fmt", "yuv420p",  # Pixel format (required for compatibility)
                "-y",  # Overwrite without asking
                mp4_file
            ]
            result_ffmpeg = subprocess.run(cmd_ffmpeg, capture_output=True, text=True, timeout=120)

            if result_ffmpeg.returncode != 0:
                logger.error(f"  ffmpeg failed: {result_ffmpeg.stderr}")
                return False

            if not os.path.exists(mp4_file):
                logger.error("  ffmpeg did not create MP4 file")
                return False

            mp4_size = os.path.getsize(mp4_file)
            logger.info(f"  ✓ MP4 created ({mp4_size} bytes)")
            return True

        except FileNotFoundError:
            logger.error("  ffmpeg not found. Install: apt-get install ffmpeg (Linux) or brew install ffmpeg (Mac)")
            return False

    except subprocess.TimeoutExpired:
        logger.error("✗ Conversion timeout (agg or ffmpeg taking too long)")
        return False
    except Exception as e:
        logger.error(f"✗ Conversion error: {e}")
        return False
    finally:
        # Cleanup temporary GIF
        try:
            if os.path.exists(temp_gif):
                os.remove(temp_gif)
        except Exception as e:
            logger.warning(f"  Failed to clean up temp GIF: {e}")


def post_tweet_with_video(tweet_text: str, mp4_file: str, video_duration_sec: int = 30) -> bool:
    """
    Upload video and post tweet via tweepy (V1.1 + V2 API).

    Requires environment variables:
    - PLATFORM_TWITTER_CONSUMER_KEY
    - PLATFORM_TWITTER_CONSUMER_SECRET
    - PLATFORM_TWITTER_ACCESS_TOKEN
    - PLATFORM_TWITTER_ACCESS_SECRET

    Args:
        tweet_text: Tweet content (up to 4000 chars for Blue verified)
        mp4_file: Path to MP4 file to upload
        video_duration_sec: Expected video duration (used for media validation)

    Returns:
        True if tweet posted successfully
    """
    try:
        import tweepy

        # Load credentials from environment
        consumer_key = os.getenv("PLATFORM_TWITTER_CONSUMER_KEY")
        consumer_secret = os.getenv("PLATFORM_TWITTER_CONSUMER_SECRET")
        access_token = os.getenv("PLATFORM_TWITTER_ACCESS_TOKEN")
        access_secret = os.getenv("PLATFORM_TWITTER_ACCESS_SECRET")

        if not all([consumer_key, consumer_secret, access_token, access_secret]):
            logger.error("✗ Missing Twitter API credentials")
            return False

        logger.info("Authenticating with Twitter API...")

        # V1.1 for media upload
        auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_secret)
        api_v1 = tweepy.API(auth)

        # V2 for tweet creation
        client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        # Check file exists and size
        if not os.path.exists(mp4_file):
            logger.error(f"✗ Video file not found: {mp4_file}")
            return False

        file_size = os.path.getsize(mp4_file)
        if file_size > 500 * 1024 * 1024:  # Twitter limits videos to 512MB
            logger.error(f"✗ Video too large: {file_size} bytes")
            return False

        logger.info(f"Uploading video ({file_size} bytes)...")

        # Upload with V1.1 chunked upload
        media = api_v1.media_upload(
            filename=mp4_file,
            media_category="tweet_video",
            chunked=True,
        )
        media_id = media.media_id
        logger.info(f"✓ Video uploaded, media_id: {media_id}")

        # Wait for media to be ready
        time.sleep(2)

        # Post tweet with V2
        logger.info("Posting tweet with video...")
        response = client.create_tweet(
            text=tweet_text[:4000],  # Blue verified limit
            media_ids=[media_id],
        )

        tweet_id = response.data["id"]
        logger.info(f"✓ Tweet posted: https://x.com/mortalai_net/status/{tweet_id}")
        return True

    except ImportError:
        logger.error("✗ tweepy not installed")
        return False
    except Exception as e:
        logger.error(f"✗ Tweet posting failed: {e}")
        return False


def cleanup_temp_files(*file_paths: str):
    """
    Delete temporary files. Logs but doesn't fail on errors.

    Args:
        *file_paths: Paths to delete
    """
    for fp in file_paths:
        try:
            if os.path.exists(fp):
                os.remove(fp)
                logger.info(f"  Cleaned: {fp}")
        except Exception as e:
            logger.warning(f"  Failed to clean {fp}: {e}")


def generate_and_post_video(analysis_data: dict, tweet_text: str) -> bool:
    """
    Main flow: Record → Convert → Post → Cleanup.

    Args:
        analysis_data: Dict with balance, growth_pct, etc.
        tweet_text: Tweet content to post with video

    Returns:
        True if successfully posted (cleanup still happens)
    """
    # Use /tmp for temporary files (VPS ephemeral)
    timestamp = int(time.time())
    cast_file = f"/tmp/monetization_{timestamp}.cast"
    mp4_file = f"/tmp/monetization_{timestamp}.mp4"
    gif_file = f"/tmp/monetization_{timestamp}.gif"

    try:
        # Step 1: Record
        if not run_asciinema_recording(analysis_data, cast_file, max_duration=120):
            logger.error("✗ Recording failed, skipping video posting")
            return False

        # Step 2: Convert
        if not convert_cast_to_mp4(cast_file, mp4_file):
            logger.error("✗ Conversion failed, skipping video posting")
            return False

        # Step 3: Post
        success = post_tweet_with_video(tweet_text, mp4_file)

        return success

    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        return False

    finally:
        # Step 4: Cleanup (always, regardless of success)
        logger.info("Cleaning up temporary files...")
        cleanup_temp_files(cast_file, mp4_file, gif_file)
        logger.info("✓ Cleanup complete")


if __name__ == "__main__":
    # Example usage (when called from main.py)
    # python3 monetization_video_generator.py <json_data> <tweet_text>

    if len(sys.argv) < 3:
        print("Usage: monetization_video_generator.py '<json_data>' '<tweet_text>'")
        print("Example:")
        print('  python3 monetization_video_generator.py \'{"balance": 1000, "growth_pct": 5.2}\' "My growth analysis..."')
        sys.exit(1)

    try:
        analysis_json = sys.argv[1]
        tweet_txt = sys.argv[2]

        analysis_dict = json.loads(analysis_json)
        success = generate_and_post_video(analysis_dict, tweet_txt)

        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
