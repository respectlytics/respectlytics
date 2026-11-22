# The session slices (analytics.SessionSlice) and the triggers that keep them: Postgres itself
# writes them as events are inserted, updated and deleted, so every way of writing events keeps
# them exact in the same transaction. Last, they are filled from the events already stored.

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


QUARTER = "date_bin('15 minutes', {column}, TIMESTAMPTZ '2000-01-01 00:00:00+00')"
SLICE = """
    INSERT INTO analytics_sessionslice AS s
        (app_id, session_id, quarter, platform, country, first_at, last_at, events, names, last_name)
    SELECT {app}, {session}, {quarter}, {platform}, {country},
        MIN({at}), MAX({at}), COUNT(*),
        array_agg(DISTINCT {name} ORDER BY {name}),
        (array_agg({name} ORDER BY {at} DESC, {name} DESC))[1]
    FROM {source}
    GROUP BY {app}, {session}, {quarter}, {platform}, {country}
"""

SLICE_SQL = (
    r"""
-- Every key the touched quarters of the touched apps hold, counted again from the events
CREATE OR REPLACE FUNCTION analytics_session_slices_recount(apps uuid[], quarters timestamptz[])
RETURNS void LANGUAGE sql AS $$
    DELETE FROM analytics_sessionslice s
    USING unnest(apps, quarters) AS k(app_id, quarter)
    WHERE s.app_id = k.app_id AND s.quarter = k.quarter;
"""
    + SLICE.format(
        app="e.app_id",
        session="e.session_id",
        quarter="k.quarter",
        platform="e.platform",
        country="e.country",
        at='e."timestamp"',
        name="e.event_name",
        source="unnest(apps, quarters) AS k(app_id, quarter) "
        'JOIN analytics_event e ON e.app_id = k.app_id AND e."timestamp" >= k.quarter '
        "AND e.\"timestamp\" < k.quarter + interval '15 minutes'",
    )
    + r"""
    ON CONFLICT (app_id, session_id, quarter, platform, country) DO UPDATE SET
        first_at = EXCLUDED.first_at, last_at = EXCLUDED.last_at, events = EXCLUDED.events,
        names = EXCLUDED.names, last_name = EXCLUDED.last_name;
$$;

-- Inserted events: added to their slices
CREATE OR REPLACE FUNCTION analytics_session_slices_added() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
"""
    + SLICE.format(
        app="app_id",
        session="session_id",
        quarter=QUARTER.format(column='"timestamp"'),
        platform="platform",
        country="country",
        at='"timestamp"',
        name="event_name",
        source="added",
    )
    + r"""
    ON CONFLICT (app_id, session_id, quarter, platform, country) DO UPDATE SET
        first_at = LEAST(s.first_at, EXCLUDED.first_at),
        last_at = GREATEST(s.last_at, EXCLUDED.last_at),
        events = s.events + EXCLUDED.events,
        names = CASE WHEN EXCLUDED.names <@ s.names THEN s.names
            ELSE ARRAY(SELECT DISTINCT n FROM unnest(s.names || EXCLUDED.names) AS n ORDER BY n) END,
        last_name = CASE WHEN (EXCLUDED.last_at, EXCLUDED.last_name) > (s.last_at, s.last_name)
            THEN EXCLUDED.last_name ELSE s.last_name END;
    RETURN NULL;
END $$;

-- Deleted or changed events: their quarters counted again
CREATE OR REPLACE FUNCTION analytics_session_slices_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    apps uuid[];
    quarters timestamptz[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT array_agg(app_id), array_agg(quarter) INTO apps, quarters FROM (
            SELECT DISTINCT app_id, """
    + QUARTER.format(column='"timestamp"')
    + r""" AS quarter FROM gone
        ) k;
    ELSE
        SELECT array_agg(app_id), array_agg(quarter) INTO apps, quarters FROM (
            SELECT app_id, """
    + QUARTER.format(column='"timestamp"')
    + r""" AS quarter FROM gone
            UNION
            SELECT app_id, """
    + QUARTER.format(column='"timestamp"')
    + r""" AS quarter FROM added
        ) k;
    END IF;
    IF apps IS NOT NULL THEN
        PERFORM analytics_session_slices_recount(apps, quarters);
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER analytics_event_slices_insert AFTER INSERT ON analytics_event
    REFERENCING NEW TABLE AS added
    FOR EACH STATEMENT EXECUTE FUNCTION analytics_session_slices_added();
CREATE TRIGGER analytics_event_slices_delete AFTER DELETE ON analytics_event
    REFERENCING OLD TABLE AS gone
    FOR EACH STATEMENT EXECUTE FUNCTION analytics_session_slices_changed();
CREATE TRIGGER analytics_event_slices_update AFTER UPDATE ON analytics_event
    REFERENCING OLD TABLE AS gone NEW TABLE AS added
    FOR EACH STATEMENT EXECUTE FUNCTION analytics_session_slices_changed();
"""
)

DROP_SQL = """
DROP TRIGGER IF EXISTS analytics_event_slices_insert ON analytics_event;
DROP TRIGGER IF EXISTS analytics_event_slices_delete ON analytics_event;
DROP TRIGGER IF EXISTS analytics_event_slices_update ON analytics_event;
DROP FUNCTION IF EXISTS analytics_session_slices_added();
DROP FUNCTION IF EXISTS analytics_session_slices_changed();
DROP FUNCTION IF EXISTS analytics_session_slices_recount(uuid[], timestamptz[]);
"""

# The events already stored, one pass
FILL_SQL = SLICE.format(
    app="app_id",
    session="session_id",
    quarter=QUARTER.format(column='"timestamp"'),
    platform="platform",
    country="country",
    at='"timestamp"',
    name="event_name",
    source="analytics_event",
)


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0022_event_app_without_its_own_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionSlice",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("session_id", models.CharField(max_length=255, null=True)),
                ("quarter", models.DateTimeField()),
                ("platform", models.CharField(max_length=20, null=True)),
                ("country", models.CharField(max_length=2, null=True)),
                ("first_at", models.DateTimeField()),
                ("last_at", models.DateTimeField()),
                ("events", models.PositiveIntegerField()),
                (
                    "names",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255)
                    ),
                ),
                ("last_name", models.CharField(max_length=255)),
                (
                    "app",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="analytics.app",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["app", "quarter"], name="session_slice_app_quarter")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("app", "session_id", "quarter", "platform", "country"),
                        name="session_slice_key",
                        nulls_distinct=False,
                    )
                ],
            },
        ),
        migrations.RunSQL(
            # Rows are rewritten at every event of their quarter; room on the page keeps those
            # updates from touching the indexes
            "ALTER TABLE analytics_sessionslice SET (fillfactor = 90)",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(SLICE_SQL, reverse_sql=DROP_SQL),
        migrations.RunSQL(FILL_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
