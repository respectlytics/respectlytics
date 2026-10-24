#!/bin/bash
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Creating cache table..."
python manage.py createcachetable 2>/dev/null || true

echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

# GeoIP database: DB-IP's free one, or MaxMind's when MaxMind credentials are given. It is kept
# in a volume and downloaded again only when it is more than 30 days old.
echo "Checking the GeoIP database..."
python manage.py update_geoip || echo "GeoIP download failed (non-fatal, geolocation will be disabled)"

echo ""
echo "============================================"
echo "  Respectlytics Community Edition is ready!"
echo "  http://localhost:${PORT:-8080}"
echo "============================================"
echo ""

exec "$@"
