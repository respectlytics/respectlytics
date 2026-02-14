#!/bin/bash
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Creating cache table..."
python manage.py createcachetable 2>/dev/null || true

echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

# Download GeoIP database if MaxMind credentials are provided
if [ -n "$MAXMIND_ACCOUNT_ID" ] && [ -n "$MAXMIND_LICENSE_KEY" ]; then
    echo "Downloading GeoIP database..."
    python manage.py update_geoip || echo "GeoIP download failed (non-fatal, geolocation will be disabled)"
fi

echo ""
echo "============================================"
echo "  Respectlytics Community Edition is ready!"
echo "  http://localhost:${PORT:-8080}"
echo "============================================"
echo ""

exec "$@"
