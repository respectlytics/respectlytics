"""The suite always runs on fresh databases.

Each run creates the test database and, with --parallel, one copy per worker, migrates them and
drops them at the end. A database left behind by a run that crashed is dropped without asking,
because a run with no keyboard (CI) cannot answer Django's question. A database kept between
runs would keep the workers' copies as they were, so a new migration would never reach them.
The suite needs a PostgreSQL role that may create and drop databases.
"""

from django.test.runner import DiscoverRunner


class FreshDatabaseTestRunner(DiscoverRunner):
    def __init__(self, *args, **kwargs):
        kwargs["keepdb"] = False
        kwargs["interactive"] = False
        super().__init__(*args, **kwargs)
