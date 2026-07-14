#!/bin/bash
set -e

echo "=== Waiting for PostgreSQL ==="
for i in {1..30}; do
    if PGPASSWORD=admin123 psql -h db -U titanpay_user -d titanpay_db -c "SELECT 1" > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "Waiting for PostgreSQL... (attempt $i/30)"
    sleep 2
done

echo "=== Running migrations ==="
python manage.py migrate --no-input

echo "=== Collecting static files ==="
python manage.py collectstatic --no-input --clear

echo "=== Killing old gunicorn processes ==="
pkill -f gunicorn || true
sleep 2

echo "=== Starting Gunicorn ==="
exec gunicorn --bind 0.0.0.0:8080 --workers=2 --timeout 120 titanpay.wsgi:application
