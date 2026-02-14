# Respectlytics Community Edition — Reference Documentation

This document provides detailed technical documentation for the Respectlytics Community Edition. For quick start instructions, see [README.md](../README.md).

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [API Endpoints (Detailed)](#api-endpoints-detailed)
3. [Authentication](#authentication)
4. [Environment Variables (Complete)](#environment-variables-complete)
5. [Manual Installation](#manual-installation)
6. [Admin Panel & OTP Setup](#admin-panel--otp-setup)
7. [Backup & Restore](#backup--restore)
8. [Scaling](#scaling)
9. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Django Apps

| App | Purpose |
|-----|---------|
| `analytics` | Core analytics API — event ingestion, queries, export, deletion, geo-lookup |
| `conversion` | Conversion Intelligence — DAU, funnels, drop-off analysis, correlation |
| `dashboard` | Authenticated web dashboard for viewing analytics |
| `users` | User authentication — registration, login, email verification, account management |
| `core` | Django project configuration (settings, URLs, WSGI) |

### Data Flow

```
Mobile App (SDK)
    ↓ POST /api/v1/events/  (X-App-Key header)
    ↓
Respectlytics Server
    ├── IP → Country lookup (GeoIP, transient)
    ├── Validate & store event (5 fields only)
    └── Discard IP immediately
    ↓
PostgreSQL Database
    ↓
Dashboard (browser)  ← Session auth
API queries          ← App key auth
```

### Key Technical Decisions

- **PostgreSQL only:** Uses `django.contrib.postgres` aggregates (e.g., `ArrayAgg`). SQLite will not work.
- **Session-based analytics:** No persistent user IDs. Session IDs rotate every 2 hours.
- **5-field storage:** Only `event_name`, `session_id`, `timestamp`, `platform`, `country` are stored. Additional fields are silently ignored.
- **Unlimited events:** Community Edition has no event quotas. All events are accepted.

---

## API Endpoints (Detailed)

### Event Ingestion

#### `POST /api/v1/events/`

Create a new analytics event.

**Authentication:** App key (`X-App-Key` header)

**Request Body:**

```json
{
    "event_name": "app_opened",
    "session_id": "hashed-session-id",
    "platform": "ios",
    "timestamp": "2025-02-14T10:30:00Z",
    "country": "SE"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `event_name` | Yes | Name of the event |
| `session_id` | Yes | Client-generated session identifier |
| `platform` | No | Platform string (e.g., `ios`, `android`) |
| `timestamp` | No | ISO 8601 timestamp (defaults to server time) |
| `country` | No | ISO 3166-1 alpha-2 country code (auto-detected from IP if omitted) |

**Response (201 Created):**

```json
{
    "id": 12345,
    "event_name": "app_opened",
    "timestamp": "2025-02-14T10:30:00Z",
    "message": "Event created successfully"
}
```

---

### Event Queries

#### `GET /api/v1/events/summary/`

Aggregated event summary with time-series data.

**Authentication:** App key

**Query Parameters:**

| Parameter | Description | Default |
|-----------|-------------|---------|
| `time_range` | Minutes of data to include | `1440` (24 hours) |
| `granularity` | Time bucket size (`hour`, `day`, `week`, `month`) | Auto |
| `timezone` | IANA timezone (e.g., `Europe/Stockholm`) | `UTC` |
| `event_name` | Filter by event name | All events |
| `platform` | Filter by platform | All platforms |
| `country` | Filter by country code | All countries |

#### `GET /api/v1/events/count/`

Total event count for the app.

#### `GET /api/v1/events/geo-summary/`

Country distribution of events.

#### `GET /api/v1/events/event-types/`

List of distinct event types with counts.

#### `GET /api/v1/events/funnel/`

Funnel analysis — conversion rates between sequential events.

**Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `steps` | Comma-separated event names defining funnel steps |
| `time_range` | Analysis time window (minutes) |
| `platform` | Filter by platform |

#### `GET /api/v1/events/filter-options/`

Available filter values (platforms, countries, event types) for the app.

#### `GET /api/v1/events/export/`

Export events as CSV download.

#### `GET /api/v1/events/recent-activity/`

Recent event activity with polling support.

---

### Conversion Intelligence

#### `GET /api/v1/analytics/dau/`

Daily Active Users (unique sessions per day).

#### `GET /api/v1/analytics/conversions/`

Conversion rate analysis.

#### `GET /api/v1/analytics/retention/`

Session retention cohort analysis.

#### `GET /api/v1/analytics/drop-off/`

Funnel drop-off point analysis.

#### `GET /api/v1/analytics/correlation/`

Event correlation analysis.

#### `GET /api/v1/analytics/segments/`

User segment analysis by platform/country.

#### `GET /api/v1/analytics/top-events/`

Most common events ranked by frequency.

#### `GET /api/v1/analytics/session-duration/`

Average session duration analysis.

#### `GET /api/v1/analytics/event-frequency/`

Event frequency distribution.

---

### App Management

#### `GET /api/v1/apps/`

List all apps for the authenticated user.

**Authentication:** Session (browser)

#### `POST /api/v1/apps/`

Create a new app.

**Authentication:** Session (browser)

**Request Body:**

```json
{
    "name": "My iOS App"
}
```

**Response:**

```json
{
    "name": "My iOS App",
    "slug": "my-ios-app",
    "app_key": "uuid-app-key-here"
}
```

#### `POST /api/v1/apps/<slug>/regenerate-key/`

Regenerate the app's API key. The old key is immediately invalidated.

---

### Data Management

#### `POST /api/v1/events/delete-preview/`

Preview which events would be deleted.

#### `DELETE /api/v1/events/delete/`

Delete events matching specified criteria.

#### `GET /api/v1/events/deletion-history/`

View history of bulk deletion operations.

---

### Utility

#### `GET /api/v1/health/`

Health check endpoint. Returns `200 OK` when the server is running.

#### `GET /api/v1/`

API root — lists available endpoints.

#### `GET /api/v1/reference/`

Interactive API documentation (ReDoc).

---

## Authentication

### App Key Authentication (SDK/API)

Mobile SDKs and API clients authenticate using an app key passed in the `X-App-Key` header:

```bash
curl -H "X-App-Key: your-app-key" https://your-server.com/api/v1/events/summary/
```

App keys are generated when you create an app in the dashboard and can be regenerated at any time.

### Session Authentication (Dashboard)

The web dashboard uses Django's session authentication. Users log in via the web interface at `/login/`.

### Rate Limiting

API endpoints are rate-limited using `django-ratelimit`. Default limits prevent abuse while allowing legitimate traffic.

---

## Environment Variables (Complete)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | Django secret key for crypto operations | `change-me-in-production` | **Yes** (production) |
| `DEBUG` | Enable Django debug mode | `True` | No |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1,0.0.0.0` | **Yes** (production) |
| `DATABASE_URL` | PostgreSQL connection string | `postgres://respectlytics:changeme@localhost:5432/respectlytics` | **Yes** |
| `POSTGRES_PASSWORD` | PostgreSQL password (Docker) | `changeme` | No |
| `PORT` | Server listen port | `8080` | No |
| `DATABASE_SSL` | Require SSL for PostgreSQL connection (enable for managed DB services) | `False` | No |
| `SECURE_SSL` | Force HTTPS redirect and secure cookies (enable behind HTTPS reverse proxy) | `False` | No |
| `ADMIN_REQUIRE_OTP` | Require TOTP 2FA for admin panel | `False` | No |
| `MAXMIND_ACCOUNT_ID` | MaxMind GeoLite2 account ID | _(empty)_ | No |
| `MAXMIND_LICENSE_KEY` | MaxMind GeoLite2 license key | _(empty)_ | No |
| `EMAIL_BACKEND` | Django email backend class | `django.core.mail.backends.console.EmailBackend` | No |
| `EMAIL_HOST` | SMTP server hostname | `localhost` | No |
| `EMAIL_PORT` | SMTP server port | `587` | No |
| `EMAIL_USE_TLS` | Use TLS for SMTP | `True` | No |
| `EMAIL_HOST_USER` | SMTP username | _(empty)_ | No |
| `EMAIL_HOST_PASSWORD` | SMTP password | _(empty)_ | No |
| `DEFAULT_FROM_EMAIL` | Sender address for outgoing email | `Respectlytics <noreply@localhost>` | No |

### Generating a Secret Key

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Manual Installation

### Step-by-step (Ubuntu/Debian)

```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev postgresql libpq-dev

# 2. Create PostgreSQL database
sudo -u postgres createuser respectlytics
sudo -u postgres createdb respectlytics -O respectlytics
sudo -u postgres psql -c "ALTER USER respectlytics PASSWORD 'your-secure-password';"

# 3. Clone repository
git clone https://github.com/respectlytics/respectlytics.git
cd respectlytics

# 4. Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# 5. Install Python dependencies
pip install -r requirements.txt

# 6. Configure environment
cp .env.example .env
# Edit .env:
#   SECRET_KEY=<random-string>
#   DATABASE_URL=postgres://respectlytics:your-secure-password@localhost:5432/respectlytics
#   DEBUG=False
#   ALLOWED_HOSTS=your-domain.com

# 7. Run migrations
python manage.py migrate

# 8. Create superuser
python manage.py createsuperuser

# 9. Collect static files
python manage.py collectstatic --noinput

# 10. Start with Gunicorn
gunicorn core.wsgi:application --bind 0.0.0.0:8080 --workers 2 --threads 3
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name analytics.example.com;

    location /static/ {
        alias /path/to/respectlytics/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Systemd Service

```ini
[Unit]
Description=Respectlytics Analytics Server
After=network.target postgresql.service

[Service]
Type=exec
User=respectlytics
Group=respectlytics
WorkingDirectory=/opt/respectlytics
ExecStart=/opt/respectlytics/venv/bin/gunicorn core.wsgi:application --bind 0.0.0.0:8080 --workers 2 --threads 3
Restart=always
RestartSec=5
EnvironmentFile=/opt/respectlytics/.env

[Install]
WantedBy=multi-user.target
```

---

## Admin Panel & OTP Setup

### Basic Access

Navigate to `/admin/` and log in with your superuser credentials.

### Enabling 2FA (TOTP)

1. Set `ADMIN_REQUIRE_OTP=True` in your environment
2. Restart the server
3. Navigate to `/admin/`
4. You'll be prompted to set up a TOTP device
5. Scan the QR code with an authenticator app (Google Authenticator, Authy, etc.)
6. Enter the verification code

### Security Dashboard

The admin panel includes a security dashboard at `/admin/security/` showing:
- Failed login attempts
- Locked accounts
- Rate limit status
- IP ban management

---

## Backup & Restore

### Backup

```bash
# Full database backup
pg_dump -h localhost -U respectlytics respectlytics > backup_$(date +%Y%m%d).sql

# Compressed backup
pg_dump -h localhost -U respectlytics respectlytics | gzip > backup_$(date +%Y%m%d).sql.gz

# Docker
docker compose exec db pg_dump -U respectlytics respectlytics > backup_$(date +%Y%m%d).sql
```

### Restore

```bash
# Restore from backup
psql -h localhost -U respectlytics respectlytics < backup_20250214.sql

# Docker
docker compose exec -T db psql -U respectlytics respectlytics < backup_20250214.sql
```

### Automated Backups (Cron)

```bash
# Daily backup at 2 AM, keep 30 days
0 2 * * * pg_dump -h localhost -U respectlytics respectlytics | gzip > /backups/respectlytics_$(date +\%Y\%m\%d).sql.gz && find /backups -name "respectlytics_*.sql.gz" -mtime +30 -delete
```

---

## Scaling

### Gunicorn Workers

The default configuration uses 2 workers with 3 threads each. For higher traffic:

```bash
# Rule of thumb: (2 * CPU cores) + 1 workers
gunicorn core.wsgi:application --bind 0.0.0.0:8080 --workers 5 --threads 3
```

### PostgreSQL Tuning

For high-volume event ingestion:

```sql
-- Shared buffers (25% of available RAM)
ALTER SYSTEM SET shared_buffers = '2GB';

-- Work memory
ALTER SYSTEM SET work_mem = '64MB';

-- Effective cache size (75% of available RAM)
ALTER SYSTEM SET effective_cache_size = '6GB';
```

### Connection Pooling

For many concurrent connections, add PgBouncer:

```bash
pip install django-db-connection-pool
```

### Read Replicas

For read-heavy workloads, configure Django database routing with a read replica:

```python
DATABASES = {
    'default': env.db('DATABASE_URL'),
    'replica': env.db('DATABASE_REPLICA_URL'),
}
```

---

## Troubleshooting

### Server won't start

**"No module named 'billing'"**
You're running the SaaS version settings. The Community Edition should not reference billing. Check that `core/settings.py` is the Community Edition version.

**"relation does not exist"**
Run migrations: `python manage.py migrate`

**"FATAL: password authentication failed"**
Check your `DATABASE_URL` credentials.

### GeoIP not working

**Country field is empty**
GeoIP database not installed. Run `python manage.py update_geoip` with valid MaxMind credentials.

**"Unable to open database"**
The `.mmdb` file is missing or corrupted. Re-download with `python manage.py update_geoip`.

### Email not sending

**Default:** Email prints to console (`stdout`). Check your terminal output for verification links.

**SMTP:** Set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and configure SMTP credentials.

### Static files not loading

Run `python manage.py collectstatic --noinput` and ensure whitenoise is in middleware.

### Docker issues

**Port already in use:**
```bash
lsof -i :8080
kill -9 <PID>
```

**Database not ready:**
Docker Compose uses a health check. If it times out, increase the `retries` in `docker-compose.yml`.

**Container logs:**
```bash
docker compose logs web
docker compose logs db
```

---

> **Legal Disclaimer:** This information is provided for educational purposes and does not constitute legal advice. Regulations vary by jurisdiction and change over time. Consult your legal team to determine the requirements that apply to your situation.
