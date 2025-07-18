# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        build-essential \
        pkg-config && \
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
    DATA_DIR=/data \
    # Audio-specific environment variables
    PULSE_SERVER="unix:/run/user/1000/pulse/native" \
    # Network optimization
    AIOHTTP_CONNECTOR_LIMIT=100 \
    AIOHTTP_CONNECTOR_LIMIT_PER_HOST=10

# Install runtime dependencies with audio support
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Audio and multimedia
        ffmpeg=7:* \
        opus-tools \
        # SSL/TLS support
        openssl=* \
        ca-certificates=* \
        # Network tools
        curl \
        wget \
        # System monitoring
        procps=* \
        # Audio libraries
        libasound2 \
        libopus0 \
        libopus-dev \
        # Additional codec support
        libavcodec-extra \
        # Process management
        tini && \
    # Update CA certificates
    update-ca-certificates && \
    # Clean up
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Create a non-root user to run the application
RUN groupadd -g 1000 hertz && \
    useradd -u 1000 -g hertz -s /bin/bash -m hertz

# Create application directory
WORKDIR /app

# Copy wheels from builder stage
COPY --from=builder /wheels /wheels

# Install Python packages from wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application files
COPY --chown=hertz:hertz . .

# Create data directories and set permissions
RUN mkdir -p /data/cache /data/cache/tmp /data/logs && \
    chown -R hertz:hertz /data

# Setup volume for persistent data
VOLUME ["/data"]

# Set working directory permissions
RUN chown -R hertz:hertz /app

# Create a script to test audio support
RUN echo '#!/bin/bash\n\
echo "Testing FFmpeg audio support..."\n\
ffmpeg -version | head -1\n\
echo "Testing Opus codec..."\n\
ffmpeg -codecs | grep opus || echo "Opus codec not found"\n\
echo "Testing network connectivity..."\n\
curl -s --max-time 10 https://www.google.com > /dev/null && echo "Network OK" || echo "Network issue"\n\
echo "Audio test complete"\n\
' > /app/test-audio.sh && chmod +x /app/test-audio.sh

# Switch to non-root user
USER hertz

# Add comprehensive health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD test -f /data/health_status && \
        [ $(($(date +%s) - $(cat /data/health_status))) -lt 60 ] && \
        python -c "import asyncio; import aiohttp; asyncio.run(aiohttp.ClientSession().get('https://www.google.com').close())" 2>/dev/null || exit 1

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run the bot with better error handling
CMD ["python", "-m", "hertz"]