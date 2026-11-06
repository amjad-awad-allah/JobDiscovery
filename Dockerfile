# ==========================================
# Stage 1: Build Dependencies
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ==========================================
# Stage 2: Final Minimal Production Runtime
# ==========================================
FROM python:3.12-slim AS runtime

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DB_PATH="/app/data/company_discovery.db"

# Install runtime utilities only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create dedicated unprivileged user and directories
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appgroup /app

WORKDIR /app

# Copy application source code with non-root ownership
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Healthcheck to verify database schema and runtime readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "from database import init_db; init_db('$DB_PATH')" || exit 1

# Persistent storage volume for SQLite database
VOLUME ["/app/data"]

# Default execution entrypoint and command
ENTRYPOINT ["python", "main.py"]
CMD ["--menu"]

