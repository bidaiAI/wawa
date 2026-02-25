FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    asciinema \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# agg (asciinema-agg) — convert .cast recordings to GIF/MP4
RUN curl -fsSL https://github.com/asciinema/agg/releases/download/v1.4.3/agg-x86_64-unknown-linux-gnu \
    -o /usr/local/bin/agg && chmod +x /usr/local/bin/agg

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Make start.sh executable + create data dirs
RUN chmod +x start.sh && mkdir -p data/memory data/tweets data/orders

EXPOSE 8000

# Health check (uses PORT env var, defaults to 8000)
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Railway uses start.sh via railway.toml; local docker uses main.py
CMD ["sh", "start.sh"]
