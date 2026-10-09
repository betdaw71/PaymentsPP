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

# docker compose run app <cmd> must not start a second gunicorn.
# Traefik copies service labels onto run containers, so a leftover
# `project-app-run-*` would share api.avapay.net with titanpay_app.
if [ "$#" -gt 0 ]; then
    echo "=== One-off command: $* ==="
    exec "$@"
fi

echo "=== Running migrations ==="
python manage.py migrate --no-input

echo "=== Collecting static files ==="
python manage.py collectstatic --no-input --clear
python manage.py diagnose_payment_page_deploy || true

echo "=== Killing old gunicorn processes ==="
pkill -f gunicorn || true
sleep 2

echo "=== Starting cron (expire / rates / balances) ==="
touch /var/log/cron.log
printenv | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID|LANG|PWD|GPG_KEY|_=' >> /etc/environment || true
python manage.py crontab remove 2>/dev/null || true
python manage.py crontab add
service cron start

echo "=== Starting Gunicorn ==="
exec gunicorn --bind 0.0.0.0:8080 --workers=2 --timeout 120 titanpay.wsgi:application
