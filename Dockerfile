# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – Builder
#   Install all Python dependencies into an isolated prefix so the final image
#   stays lean and never ships build-time tools (gcc, pip cache, etc.).
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Don't write .pyc files to disk; flush stdout/stderr immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build essentials needed to compile mysqlclient (C extension).
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first so Docker layer-caching kicks in
# and we don't re-download packages on every source-code change.
COPY requirements.txt .

# Install into /install so we can copy the whole tree to the runtime stage.
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – Runtime
#   Minimal image; no build tools, no pip, no cache.
#   Pygame is intentionally excluded from this stage (the Pygame UI runs
#   locally on the developer's machine, not inside Docker).
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Makes the /install site-packages visible to the interpreter.
    PYTHONPATH="/install/lib/python3.12/site-packages:${PYTHONPATH}"

WORKDIR /app

# Runtime-only system library required by mysqlclient.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Pull compiled packages from the builder stage.
COPY --from=builder /install /install

# Copy the application source code.
# The Pygame simulation (src/views/) is copied along with the rest of the
# source tree so imports don't break, but it is never executed inside Docker.
COPY . .

# ── Security: run as a non-root user ─────────────────────────────────────────
RUN addgroup --system appgroup \
 && adduser  --system --ingroup appgroup appuser \
 && chown -R appuser:appgroup /app

USER appuser

# ── Port ─────────────────────────────────────────────────────────────────────
# FastAPI / Uvicorn listens on 8000 by default.
EXPOSE 8000

# ── Health-check ─────────────────────────────────────────────────────────────
# Docker will mark the container unhealthy if the /health endpoint stops
# responding, enabling automatic restarts in production orchestrators.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
# --host 0.0.0.0   → accept connections from outside the container.
# --workers 2      → two Uvicorn workers; tune to (2 × CPU cores + 1) in prod.
# --no-access-log  → remove per-request noise; swap to --access-log for debug.
CMD ["python", "-m", "uvicorn", "src.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--no-access-log"]
