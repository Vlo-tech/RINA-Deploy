
#!/bin/bash
set -e

# This script runs the application in production using Gunicorn.

# Load environment variables from .env file
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
  echo "Error: DATABASE_URL is not set. Please add it to your .env file."
  exit 1
fi

# Run database migrations
echo "Running database migrations..."
psql "$DATABASE_URL" -f migrations.sql
echo "Migrations complete."

# Start the application with Gunicorn
echo "Starting application with Gunicorn..."
gunicorn --workers 4 --bind 0.0.0.0:5000 src.webhook_handler:app