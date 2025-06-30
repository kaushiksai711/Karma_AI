# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && pip install --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install curl for health check
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/data/karma_rewards.db \
    DATA_DIR=/data

# Create non-root user and data directory
RUN adduser --disabled-password --gecos '' appuser && \
    mkdir -p $DATA_DIR && \
    chown -R appuser:appuser $DATA_DIR && \
    chmod 755 $DATA_DIR

WORKDIR /app

# Copy only necessary files from builder
COPY --from=builder /root/.local /home/appuser/.local
COPY api/ .

# Set proper ownership of copied files
RUN chown -R appuser:appuser /app

# Ensure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Create entrypoint script to handle database permissions
RUN echo '#!/bin/sh\n\
set -e\n\
# Ensure the database directory exists and has correct permissions\n\
if [ ! -f "$DB_PATH" ]; then\n    echo "Creating database file at $DB_PATH"\n    mkdir -p "$(dirname "$DB_PATH")"\n    touch "$DB_PATH"\n    chmod 664 "$DB_PATH"\nfi\n\
# Ensure the user can write to the database file and directory\nchown -R appuser:appuser "$(dirname "$DB_PATH")" 2>/dev/null || true\nchmod 755 "$(dirname "$DB_PATH")" 2>/dev/null || true\nchown appuser:appuser "$DB_PATH" 2>/dev/null || true\nchmod 664 "$DB_PATH" 2>/dev/null || true\n\
echo "Database permissions set. Starting application..."\n\
exec "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Make entrypoint script executable
RUN chmod +x /entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Switch to non-root user
USER appuser

# Create a volume for the database
VOLUME ["/data"]

# Expose the port the app runs on
EXPOSE 8000

# Health check (fixed port number)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]