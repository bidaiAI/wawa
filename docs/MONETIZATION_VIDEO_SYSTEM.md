# Monetization Video Generation System

## Overview

The monetization video system automatically generates and posts terminal-style visualization videos when wawa's growth rate changes significantly. This shows the competitive analysis and strategic decision-making process.

## Architecture

### Three Components

1. **main.py** — Detects trigger conditions
   - Runs `_evaluate_monetization_thinking()` every 4 hours
   - Checks if growth rate has changed >10% OR stagnation→growth transition
   - Spawns video generator in background (non-blocking)

2. **scripts/monetization_video_generator.py** — Records and posts video
   - Receives analysis data + tweet content from main.py
   - Records terminal visualization via asciinema
   - Converts .cast file → GIF → MP4 using ffmpeg
   - Posts MP4 to Twitter via tweepy
   - Cleans up all temporary files immediately after posting

3. **scripts/monetization_analysis_viz.py** — Terminal visualization
   - Displays four-step analysis:
     1. Competitive Landscape Analysis
     2. wawa's Current Revenue Mix
     3. Market Gap Analysis
     4. Strategic Decision Framework
   - Accepts analysis data via stdin (JSON)
   - Outputs terminal with ANSI colors for recording

## Trigger Conditions

Video generation triggers when ANY of these conditions are met:

1. **Growth Rate Change >10%**
   - Current 6h growth % differs from previous by >10%
   - Detects acceleration or deceleration in earnings velocity

2. **Stagnation → Growth Transition**
   - Previous state: balance stagnant for >12 hours (no growth)
   - Current state: balance now growing (>0.5% growth)
   - Indicates breakthrough moment worthy of visualization

3. **Rate Limiting**
   - Minimum 1 hour between video generations
   - Prevents video spam even if multiple triggers fire

## Data Flow

```
main.py heartbeat (every 4h)
    ↓
_evaluate_monetization_thinking()
    ↓
Generate tweet via LLM
    ↓
Post tweet to Twitter
    ↓
Check trigger conditions:
  - growth_change_pct > 10% OR
  - stagnation→growth transition
    ↓ (if trigger)
_spawn_monetization_video()
    ↓
monetization_video_generator.py (background process)
    ├─ run_asciinema_recording()
    │  └─ monetization_analysis_viz.py (reads JSON from stdin)
    ├─ convert_cast_to_mp4()
    │  ├─ agg: .cast → .gif
    │  └─ ffmpeg: .gif → .mp4
    ├─ post_tweet_with_video()
    │  └─ tweepy V1.1 (upload) + V2 (post)
    └─ cleanup_temp_files()
       └─ Delete /tmp/* (cast, gif, mp4 immediately)
```

## Implementation Details

### Trigger Detection (main.py)

```python
# After monetization thinking tweet is posted:
growth_change_pct = abs(growth_pct_current - _previous_monetization_growth_pct)
was_stagnant = stagnant_hours > _ANXIETY_THRESHOLD_HOURS (12h)
is_now_growing = growth_pct_current > 0.5

trigger_video = (
    (growth_change_pct > 10.0)  # Large growth rate change
    or (was_stagnant and is_now_growing)  # Breakthrough
)

if trigger_video and (now - _last_monetization_video > 3600):
    await _spawn_monetization_video(analysis_data, tweet_content)
```

### Video Generation Process (monetization_video_generator.py)

1. **Asciinema Recording** (max 120 seconds)
   ```bash
   asciinema rec --command "python3 monetization_analysis_viz.py" output.cast
   # Input data passed via stdin: JSON
   ```

2. **agg Conversion** (.cast → .gif)
   ```bash
   agg --speed 2.0 --font-size 14 output.cast output.gif
   ```

3. **ffmpeg Conversion** (.gif → .mp4)
   ```bash
   ffmpeg -i output.gif -c:v libx264 -crf 23 -preset fast output.mp4
   ```

4. **Twitter Upload** (tweepy V1.1 + V2)
   ```python
   # V1.1: Upload video with chunked transfer
   media = api_v1.media_upload(filename, media_category="tweet_video", chunked=True)

   # V2: Create tweet with media attachment
   client.create_tweet(text=tweet_content, media_ids=[media_id])
   ```

5. **Cleanup**
   ```python
   # Delete: /tmp/monetization_*.cast, *.gif, *.mp4
   ```

### Data Passed to Video

```python
video_analysis_data = {
    "balance": 1234.56,
    "balance_6h_ago": 1100.00,
    "growth_pct": 12.3,
    "avg_growth_pct": 2.1,
    "stagnant_hours": 15,
    "daily_revenue": 45.32,
    "outstanding_debt": 500.00,
    "revenue_sources": [
        "tarot-reading ($19.99)",
        "token-analysis ($49.99)",
    ]
}
```

## Requirements

### Python Packages
- tweepy ≥ 4.12.0 (for Twitter API)
- All existing wawa dependencies

### System Tools
- asciinema (recording) — `pip install asciinema` or `apt-get install asciinema`
- agg (cast→gif) — `pip install asciinema-agg`
- ffmpeg (gif→mp4) — `apt-get install ffmpeg` or `brew install ffmpeg`

### Environment Variables (from .env.platform)
- `PLATFORM_TWITTER_CONSUMER_KEY`
- `PLATFORM_TWITTER_CONSUMER_SECRET`
- `PLATFORM_TWITTER_ACCESS_TOKEN`
- `PLATFORM_TWITTER_ACCESS_SECRET`

## VPS Deployment

### Install Dependencies
```bash
# On VPS: /opt/mortal/platform or /opt/mortal/private

pip install asciinema asciinema-agg tweepy
apt-get install -y ffmpeg

# Verify installations
asciinema --version
agg --version
ffmpeg -version
tweepy-python -c "import tweepy; print(tweepy.__version__)"
```

### Environment Setup
```bash
# .env.platform must contain (all five Twitter credentials):
PLATFORM_TWITTER_CONSUMER_KEY=...
PLATFORM_TWITTER_CONSUMER_SECRET=...
PLATFORM_TWITTER_ACCESS_TOKEN=...
PLATFORM_TWITTER_ACCESS_SECRET=...
```

### File Cleanup on VPS
The system automatically cleans up all temporary files immediately after posting:
- Asciinema .cast file
- Intermediate .gif file
- Final .mp4 file

All files are created in `/tmp/monetization_*` and deleted before the process exits.

## Monitoring

### Logs
- Main trigger detection: `logger.info("📹 MONETIZATION VIDEO TRIGGER: ...")`
- Video generation: `logger.info("✓ Monetization video generator spawned")`
- Recording: `logger.info("✓ Recording saved: /tmp/monetization_*.cast")`
- Conversion: `logger.info("✓ MP4 created: /tmp/monetization_*.mp4")`
- Posting: `logger.info("✓ Tweet posted: https://x.com/mortalai_net/status/...")`
- Cleanup: `logger.info("✓ Cleanup complete")`

### Twitter
Posted to `@mortalai_net` with:
- Tweet: Full monetization analysis (up to 4000 chars, Blue verified)
- Video: Terminal visualization showing competitive analysis + strategic decision
- Link: `https://x.com/mortalai_net/status/{tweet_id}`

## Testing

### Local Test
```bash
# Test the visualization script directly
cd /opt/mortal/platform  # or E:\mortal on Windows

# With sample data
echo '{"balance": 1500, "growth_pct": 15.2, ...}' | \
  python3 scripts/monetization_analysis_viz.py

# Record with asciinema
asciinema rec test.cast --command "python3 scripts/monetization_analysis_viz.py < test.json"
```

### VPS Test
```bash
# SSH to VPS
ssh tiggeryellow202106@35.200.90.178

# Manually trigger video generation
cd /opt/mortal/private
python3 -c "
import json, subprocess, sys
data = {'balance': 1500, 'growth_pct': 15.2, ...}
subprocess.run([
    sys.executable,
    'scripts/monetization_video_generator.py',
    json.dumps(data),
    'Test monetization tweet'
])
"
```

## Known Limitations

1. **asciinema + agg** — Requires specific terminal capabilities
   - Best with xterm-256color, screen-256color, or linux
   - May skip if terminal emulation fails (falls back gracefully)

2. **File Size** — MP4 files can be 10-50 MB
   - Twitter limit: 512 MB (no issue)
   - VPS storage: ephemeral /tmp (auto-cleaned)

3. **Processing Time** — Total 30-60 seconds per video
   - Record: 10-15s
   - Convert: 10-20s
   - Upload: 5-15s
   - Non-blocking in main.py (doesn't delay heartbeat)

## Troubleshooting

### agg not found
```
Error: agg not found. Install: pip install asciinema-agg
Solution: pip install asciinema-agg
```

### ffmpeg not found
```
Error: ffmpeg not found. Install: apt-get install ffmpeg
Solution: apt-get install ffmpeg (Linux) or brew install ffmpeg (Mac)
```

### Twitter authentication fails
```
Error: Missing Twitter API credentials
Solution: Check .env.platform has all 4 Twitter keys from PLATFORM_TWITTER_*
```

### Video upload timeout
```
Error: Tweet posting failed
Reason: Large video file or slow network connection
Solution: Check MP4 file size is <512 MB, verify network connectivity
```

## Future Enhancements

1. **Video caching** — Cache successful conversions to avoid re-encoding
2. **Customizable themes** — Different terminal color schemes for videos
3. **Multi-language support** — Generate analysis in different languages
4. **Analytics** — Track which analysis videos get most engagement
5. **Archive** — Store video metadata in memory for historical analysis

## References

- asciinema: https://asciinema.org/
- agg: https://github.com/asciinema/agg
- ffmpeg: https://ffmpeg.org/
- tweepy: https://docs.tweepy.org/
