"""The suite always runs on fresh databases.

Each run creates the test database and, with --parallel, one copy per worker, migrates them and
drops them at the end. A database left behind by a run that crashed is dropped without asking,
because the deploy gate and CI have no keyboard to answer Django's question.

Until 2026-10-22 this runner did the opposite, keeping the database between runs, because
DigitalOcean's managed PostgreSQL refused CREATE and DROP DATABASE. With --parallel that kept
the workers' copies as they were, so a new migration never reached them and the suite failed
on a missing table. The suite now runs only on PostgreSQL we run ourselves: locally, CI's
service container and the deploy gate.
"""

from django.test.runner import DiscoverRunner


class FreshDatabaseTestRunner(DiscoverRunner):
    def __init__(self, *args, **kwargs):
        kwargs["keepdb"] = False
        kwargs["interactive"] = False
        super().__init__(*args, **kwargs)
