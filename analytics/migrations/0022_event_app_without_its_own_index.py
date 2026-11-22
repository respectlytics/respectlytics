# The app's own index on Event goes: every other index on Event starts with app, and
# (app, timestamp) serves what it did. Only the index is dropped; Django's AlterField would also
# drop and re-add the foreign key, which re-checks every event under a lock.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0021_event_app_country_platform"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'DROP INDEX IF EXISTS "analytics_event_app_id_6644941a"',
                    reverse_sql='CREATE INDEX IF NOT EXISTS "analytics_event_app_id_6644941a" '
                    'ON "analytics_event" ("app_id")',
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="event",
                    name="app",
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="analytics.app",
                    ),
                ),
            ],
        ),
    ]
