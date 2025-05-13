#!/bin/bash
set -euo pipefail

# Set the application root
APP_ROOT=${APP_ROOT:-/app}
if [ ! -d "$APP_ROOT" ]; then
  APP_ROOT=$(pwd)
fi
cd "$APP_ROOT"

echo "Setting up directories..."
for dir in media staticfiles data logs; do
  mkdir -p "$dir"
done

# Setup uploads directory
mkdir -p "media/uploads"
chmod -R 777 "media/uploads"

# Set permissions for directories
chmod -R 777 media staticfiles data logs || echo "Warning: Permission setting issue"

# Function to wait for services
wait_for_service() {
  local host=$1
  local port=$2
  local max_attempts=30
  local attempt=1
  
  echo "Waiting for ${host}:${port}..."
  while ! nc -z "$host" "$port" && [ $attempt -le $max_attempts ]; do
    sleep 2
    attempt=$((attempt+1))
  done
  
  if [ $attempt -gt $max_attempts ]; then
    echo "Service ${host}:${port} not available after 60s"
    return 1
  fi
  
  echo "${host}:${port} is available"
  return 0
}

# Wait for required services
wait_for_service redis 6379 || exit 1

# Run Django management commands
echo "Running Django setup..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

# Start Gunicorn
echo "Starting Gunicorn server..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --reload
