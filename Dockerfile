FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — install requirements then force pydantic v2
# (web3 may pull pydantic v1 as transitive dep, we override it)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --force-reinstall "pydantic>=2.5.0,<3.0" "pydantic-settings>=2.1.0,<3.0"

# App code
COPY . .

# Make start.sh executable + create data dirs
RUN chmod +x start.sh && mkdir -p data/memory data/tweets data/orders

EXPOSE 8000

# Health check
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Railway uses start.sh via railway.toml; local docker uses main.py
CMD ["sh", "start.sh"]
