from django.db import migrations, models, connection


def add_max_iterations_if_missing(apps, schema_editor):
    """
    Idempotent: only add the column if it doesn't already exist.
    Handles the case where a previous (failed) migration already created this column.
    """
    from django.db import connection as conn
    with conn.cursor() as cursor:
        cursor.execute("PRAGMA table_info(graphcontrol_rule)")
        columns = [row[1] for row in cursor.fetchall()]
    if 'max_iterations' not in columns:
        schema_editor.execute(
            "ALTER TABLE graphcontrol_rule ADD COLUMN max_iterations integer NULL"
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('graphcontrol', '0008_remove_projection_unique_seed_projection_per_node_and_more'),
    ]

    operations = [
        migrations.RunPython(add_max_iterations_if_missing, noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='rule',
                    name='max_iterations',
                    field=models.PositiveIntegerField(
                        null=True,
                        blank=True,
                        help_text=(
                            'Only for controller (FBO) rules. '
                            'None = infinite (agent decides exit). '
                            'N = MS15 forces loop exit after N completed iterations.'
                        ),
                    ),
                ),
            ],
            database_operations=[],  # Already handled by RunPython above
        ),
    ]
