# Generated by Django 2.2.28 on 2023-05-12 17:33

import django.utils.timezone
from django.db import migrations, models

import sentry.db.models.fields.bounded
import sentry.db.models.fields.picklefield
from sentry.new_migrations.migrations import CheckedMigration


class Migration(CheckedMigration):
    # This flag is used to mark that a migration shouldn't be automatically run in production. For
    # the most part, this should only be used for operations where it's safe to run the migration
    # after your code has deployed. So this should not be used for most operations that alter the
    # schema of a table.
    # Here are some things that make sense to mark as dangerous:
    # - Large data migrations. Typically we want these to be run manually by ops so that they can
    #   be monitored and not block the deploy for a long period of time while they run.
    # - Adding indexes to large tables. Since this can take a long time, we'd generally prefer to
    #   have ops run this and not block the deploy. Note that while adding an index is a schema
    #   change, it's completely safe to run the operation after the code has deployed.
    is_dangerous = False

    dependencies = [
        ("sentry", "0439_backfill_notificationsetting"),
    ]

    operations = [
        migrations.CreateModel(
            name="ControlOption",
            fields=[
                (
                    "id",
                    sentry.db.models.fields.bounded.BoundedBigAutoField(
                        primary_key=True, serialize=False
                    ),
                ),
                ("key", models.CharField(max_length=128, unique=True)),
                ("last_updated", models.DateTimeField(default=django.utils.timezone.now)),
                ("value", sentry.db.models.fields.picklefield.PickledObjectField(editable=False)),
            ],
            options={
                "db_table": "sentry_controloption",
            },
        ),
    ]
