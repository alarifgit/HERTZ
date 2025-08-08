# Hertz Discord Music Bot - Dockerfile
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "bot.py"]