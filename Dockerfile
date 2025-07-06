# Enhanced Dockerfile for Trading Bot with Token Persistence
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies including curl for health check
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies with better caching
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories for data persistence
RUN mkdir -p /app/data && \
    mkdir -p /app/logs

# Create a non-root user with proper permissions
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/data && \
    chmod -R 755 /app/logs

# Switch to non-root user
USER appuser

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Add comprehensive health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/status || exit 1

# Add signal handling for graceful shutdown
STOPSIGNAL SIGTERM

# Default command - start the Flask server with better configuration
CMD ["python", "-u", "main.py"]