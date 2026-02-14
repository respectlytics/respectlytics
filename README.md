<p align="center">
  <img src="static/images/respectlytics-logo.png" alt="Respectlytics" width="200">
</p>

<h1 align="center">Respectlytics Community Edition</h1>

<p align="center">
  Privacy-first mobile analytics server. Self-hosted, session-based, 5-field storage.
  <br>No personal data retained.
</p>

<p align="center">
  <a href="#quick-start-docker">Quick Start</a> •
  <a href="#api-reference">API Reference</a> •
  <a href="#sdk-integration">SDKs</a> •
  <a href="#configuration">Configuration</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## What is Respectlytics?

Respectlytics helps developers avoid collecting personal data in the first place. Our motto is **Return of Avoidance (ROA)** — we believe the best way to handle sensitive data is to never collect it.

We use anonymized identifiers stored only in device memory (RAM) that rotate automatically every two hours or upon app restart. IP addresses are processed transiently for approximate country lookup and immediately discarded — no personal data is ever persisted.

**Only 5 fields are stored per event:**

| Field | Description |
|-------|-------------|
| `event_name` | Name of the analytics event |
| `session_id` | Anonymized session identifier (RAM-only, rotates every 2 hours) |
| `timestamp` | When the event occurred |
| `platform` | Device platform (iOS, Android, etc.) |
| `country` | Approximate country (derived from IP, IP never stored) |

Our system is **transparent** about exactly what data is collected, **defensible** because we minimize data by design, and **clear** about why each field exists. Consult your legal team to determine your specific requirements.

---

## Quick Start (Docker)

Get a running instance in under 2 minutes:

```bash
# 1. Clone the repository
git clone https://github.com/respectlytics/respectlytics.git
cd respectlytics

# 2. Copy environment file
cp .env.example .env

# 3. Generate a secret key
python3 -c "from secrets import token_urlsafe; print(f'SECRET_KEY={token_urlsafe(50)}')" >> .env

# 4. Start the services
docker compose up -d

# 5. Create your admin account
docker compose exec web python manage.py createsuperuser
```

Open [http://localhost:8080](http://localhost:8080) — you're ready to go.

---

## Quick Start (Manual)

### Prerequisites

- Python 3.12+
- PostgreSQL 14+ (required — SQLite is not supported)
- Node.js 18+ (only for Tailwind CSS development)

### Setup

```bash
# Clone and enter
git clone https://github.com/respectlytics/respectlytics.git
cd respectlytics

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY at minimum

# Run migrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput

# Start the server
gunicorn core.wsgi:application --bind 0.0.0.0:8080 --workers 2 --threads 3
```

> **Important:** PostgreSQL is required. We use `django.contrib.postgres` aggregates (e.g., `ArrayAgg`) that are not available in SQLite.

---

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for the complete list.

### Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | `change-me-in-production` |
| `DATABASE_URL` | PostgreSQL connection string | `postgres://respectlytics:changeme@localhost:5432/respectlytics` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1` |
| `PORT` | Server port | `8080` |
| `DATABASE_SSL` | Require SSL for PostgreSQL connection | `False` |
| `SECURE_SSL` | Force HTTPS redirect (enable behind reverse proxy) | `False` |
| `ADMIN_REQUIRE_OTP` | Require 2FA for admin access | `False` |
| `MAXMIND_ACCOUNT_ID` | MaxMind account for GeoIP | _(empty)_ |
| `MAXMIND_LICENSE_KEY` | MaxMind license for GeoIP | _(empty)_ |
| `EMAIL_BACKEND` | Django email backend | `console` (prints to stdout) |
| `EMAIL_HOST` | SMTP server host | `localhost` |
| `EMAIL_PORT` | SMTP server port | `587` |
| `EMAIL_USE_TLS` | Use TLS for email | `True` |
| `EMAIL_HOST_USER` | SMTP username | _(empty)_ |
| `EMAIL_HOST_PASSWORD` | SMTP password | _(empty)_ |
| `DEFAULT_FROM_EMAIL` | From address for outgoing email | `Respectlytics <noreply@localhost>` |

> **Production:** Always set `SECRET_KEY` to a random string, `DEBUG=False`, and `ALLOWED_HOSTS` to your domain.
> If running behind an HTTPS reverse proxy (nginx, Caddy), also set `SECURE_SSL=True`.
> If using managed PostgreSQL (AWS RDS, DigitalOcean), also set `DATABASE_SSL=True`.

---

## GeoIP Setup

Country detection is optional but recommended. It uses the free MaxMind GeoLite2 database.

1. Create a free account at [maxmind.com/en/geolite2/signup](https://www.maxmind.com/en/geolite2/signup)
2. Generate a license key in your MaxMind account
3. Set the environment variables:
   ```bash
   MAXMIND_ACCOUNT_ID=your_account_id
   MAXMIND_LICENSE_KEY=your_license_key
   ```
4. Download the database:
   ```bash
   python manage.py update_geoip
   ```

With Docker, the GeoIP database is downloaded automatically on container startup when credentials are provided.

Without GeoIP, events will have `country=null` — everything else works normally.

---

## API Reference

The built-in API reference is available at `/api/v1/reference/` when the server is running.

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/events/` | Ingest an analytics event |
| `GET` | `/api/v1/events/summary/` | Aggregated event summary |
| `GET` | `/api/v1/events/geo-summary/` | Country distribution |
| `GET` | `/api/v1/events/event-types/` | List event types |
| `GET` | `/api/v1/events/funnel/` | Funnel analysis |
| `GET` | `/api/v1/events/export/` | Export events (CSV) |
| `GET` | `/api/v1/analytics/dau/` | Daily active users |
| `GET` | `/api/v1/analytics/conversions/` | Conversion data |
| `GET` | `/api/v1/health/` | Health check |

### Authentication

**SDK / API endpoints** use app key authentication via the `X-App-Key` header:

```bash
curl -X POST https://your-server.com/api/v1/events/ \
  -H "Content-Type: application/json" \
  -H "X-App-Key: your-app-key-here" \
  -d '{"event_name": "app_opened", "session_id": "abc123", "platform": "ios"}'
```

**Dashboard** uses session-based authentication (login via browser).

For detailed API documentation, see [docs/REFERENCE.md](docs/REFERENCE.md).

---

## SDK Integration

Official SDKs for mobile platforms:

| Platform | Repository |
|----------|-----------|
| Swift (iOS/macOS) | [respectlytics-swift](https://github.com/nickloheden/respectlytics-swift) |
| Flutter | [respectlytics-flutter](https://github.com/nickloheden/respectlytics-flutter) |
| React Native | [respectlytics-react-native](https://github.com/nickloheden/respectlytics-react-native) |
| Kotlin (Android) | [respectlytics-kotlin](https://github.com/nickloheden/respectlytics-kotlin) |

SDK documentation: [https://respectlytics.com/sdk/](https://respectlytics.com/sdk/)

### SDK Public API

```
configure(appKey, serverUrl)  — Initialize the SDK
track(eventName)              — Track an analytics event
flush()                       — Force send queued events
```

> **Note:** There is no `identify()` or `reset()` method. Respectlytics uses session-based analytics only — no persistent user tracking.

---

## Data Retention

By default, events are stored indefinitely. Use the `purge_old_events` management command to clean up old data:

```bash
# Preview what would be deleted (no changes made)
python manage.py purge_old_events --dry-run

# Delete events older than 730 days (default)
python manage.py purge_old_events

# Delete events older than 365 days
python manage.py purge_old_events --days 365
```

### Automated Cleanup (Cron)

```bash
# Run weekly on Sunday at 3 AM
0 3 * * 0 cd /app && python manage.py purge_old_events >> /var/log/respectlytics/purge.log 2>&1
```

With Docker:
```bash
docker compose exec web python manage.py purge_old_events
```

---

## Privacy Architecture

Respectlytics helps developers avoid collecting personal data in the first place.

### What We Collect

| Field | Why | Stored? |
|-------|-----|---------|
| `event_name` | Analytics tracking | Yes |
| `session_id` | Group events within a session | Yes (anonymized, rotates every 2 hours) |
| `timestamp` | Time-series analysis | Yes |
| `platform` | Platform breakdown | Yes |
| `country` | Geographic distribution | Yes (approximate, from IP) |
| IP address | Country lookup only | **No** — processed transiently, immediately discarded |

### What We Don't Collect

- No user IDs or persistent identifiers
- No device IDs or advertising IDs
- No precise location (country only)
- No personal information
- No cross-session tracking
- No cookies or local storage

### Design Principles

- **Return of Avoidance (ROA):** Avoid collecting data you don't need
- **RAM-only identifiers:** Session IDs never written to disk on the device
- **2-hour rotation:** Session IDs automatically rotate
- **New session on restart:** Each app launch is a fresh start
- **Strict 5-field storage:** API rejects any extra data

> **Legal Disclaimer:** This information is provided for educational purposes and does not constitute legal advice. Regulations vary by jurisdiction and change over time. Consult your legal team to determine the requirements that apply to your situation.

---

## Admin Panel

Access the admin panel at `/admin/`. By default, no 2FA is required.

To enable 2FA (TOTP) for admin access:

```bash
ADMIN_REQUIRE_OTP=True
```

See [docs/REFERENCE.md](docs/REFERENCE.md) for OTP setup instructions.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

All contributors must sign a Contributor License Agreement (CLA) via [cla-assistant.io](https://cla-assistant.io).

---

## License

Respectlytics Community Edition is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

This means you can:
- Use it freely for any purpose
- Modify and distribute it
- Self-host it for your organization

If you modify the software and provide it as a network service, you must make your modifications available under the same license.

**Commercial licensing** is available for organizations whose license is incompatible with AGPL. Contact [respectlytics@loheden.com](mailto:respectlytics@loheden.com).

---

## Managed Version

Don't want to self-host? **[Respectlytics Cloud](https://respectlytics.com)** offers:

- Fully managed infrastructure
- Automatic GeoIP updates
- Built-in data retention policies
- Priority support
- No server maintenance

[Start free →](https://respectlytics.com)

---

<p align="center">
  <sub>Built with privacy in mind. Return of Avoidance (ROA).</sub>
</p>
