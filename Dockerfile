# Stage 1: Builder
# This stage installs all dependencies, including build-time tools.
FROM python:3.11-slim AS builder

# Install build-time and runtime system dependencies, and update packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc git \
    ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Create a virtual environment to isolate dependencies
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy requirements and install Python packages into the virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: Final Image
# This stage creates the final, lean image for production.
FROM python:3.11-slim

# Create a non-root user
RUN useradd --create-home appuser

# Install ONLY runtime system dependencies and patch vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Copy the virtual environment with installed packages from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Set up the application directory
WORKDIR /app
COPY listings.json .
COPY ./src ./src

# Change ownership to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Activate the virtual environment and set other environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Set the command to run the application
CMD ["gunicorn", "-b", "0.0.0.0:5000", "src.webhook_handler:app", "--workers=2", "--timeout=120"]
