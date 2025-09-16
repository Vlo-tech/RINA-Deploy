# Dockerfile - builds the webhook app
FROM python:3.11-slim

WORKDIR /app

# Create a non-root user
RUN useradd --create-home appuser

# system deps for some libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc ffmpeg libsndfile1 curl git && \

    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY listings.json /app/listings.json

RUN pip install --no-cache-dir -r /app/requirements.txt

# copy source
COPY ./src /app/src

# Change ownership of the app directory
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# default port 5000 (Flask)
EXPOSE 5000

# CMD ["python", "webhook_handler.py"]
# For production with gunicorn:
CMD ["gunicorn", "-b", "0.0.0.0:5000", "src.webhook_handler:app", "--workers=2", "--timeout=120"]
