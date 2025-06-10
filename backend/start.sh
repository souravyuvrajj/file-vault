#!/bin/bash
set -euo pipefail

# Wait for Redis service
host="redis"
port="6379"
max_attempts=30
attempt=1

echo "Waiting for ${host}:${port}..."
while ! nc -z "$host" "$port" && [ $attempt -le $max_attempts ]; do
    sleep 2
    attempt=$((attempt+1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "Service ${host}:${port} not available after 60s"
    exit 1
fi
echo "${host}:${port} is available"

# Run Django management commands
echo "Running Django setup..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Start the application
python manage.py collectstatic --noinput --clear
gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3
echo "Starting Gunicorn server..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --reload
