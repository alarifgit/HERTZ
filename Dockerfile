# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

# Install build dependencies if needed
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy and install requirements
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONPATH=/app \
    DATA_DIR=/data

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg=7:* \
        openssl=* \
        ca-certificates=* \
        procps=* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application
RUN groupadd -g 1000 hertz && \
    useradd -u 1000 -g hertz -s /bin/bash -m hertz

# Create application directory
WORKDIR /app

# Copy wheels from builder stage
COPY --from=builder /wheels /wheels

# Install Python packages from wheels
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application files
COPY --chown=hertz:hertz . .

# Create data directories and set permissions
RUN mkdir -p /data/cache /data/cache/tmp && \
    chown -R hertz:hertz /data

# Setup volume for persistent data
VOLUME ["/data"]

# Set working directory permissions
RUN chown -R hertz:hertz /app

# Switch to non-root user
USER hertz

# Add health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=15s --retries=3 \
    CMD test -f /data/health_status && [ $(($(date +%s) - $(cat /data/health_status))) -lt 30 ] || exit 1

# Run the bot
CMD ["python", "-m", "hertz"]