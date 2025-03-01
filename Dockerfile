FROM python:3.12-slim

# Install ffmpeg and needed dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg openssl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directories
RUN mkdir -p /data/cache /data/cache/tmp

# Setup volume for persistent data
VOLUME ["/data"]
ENV DATA_DIR=/data

# Set Python to use UTF-8 by default
ENV PYTHONIOENCODING=utf-8

# Run the bot
CMD ["python", "-m", "hertz"]