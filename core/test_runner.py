"""
Custom test runner for managed PostgreSQL environments.

DigitalOcean (and similar) managed PostgreSQL services block access to the
'postgres' system database, which Django needs for CREATE/DROP DATABASE.
This causes `manage.py test` to hang indefinitely.

Solution: Always pass keepdb=True so Django reuses the existing test database
and only applies pending migrations instead of recreating it from scratch.

The test database must be created once manually via the hosting provider's
console (e.g., DigitalOcean → Databases → Users & Databases → Add Database).
"""
from django.test.runner import DiscoverRunner


class KeepDbTestRunner(DiscoverRunner):
    """Test runner that always reuses the existing test database."""

    def __init__(self, *args, **kwargs):
        kwargs['keepdb'] = True
        super().__init__(*args, **kwargs)
