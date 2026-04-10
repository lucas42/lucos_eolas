from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("metadata", "0031_festival_commemorates"),
    ]

    operations = [
        migrations.RunSQL(
            # Drop the unique constraint or index on wikipedia_slug — either may exist
            # depending on the Django version that first created the table.
            sql="""
                ALTER TABLE metadata_historicalevent
                DROP CONSTRAINT IF EXISTS metadata_historicalevent_wikipedia_slug_key;
                DROP INDEX IF EXISTS metadata_historicalevent_wikipedia_slug_key;
            """,
            reverse_sql="""
                CREATE UNIQUE INDEX metadata_historicalevent_wikipedia_slug_key
                ON metadata_historicalevent (wikipedia_slug);
            """,
        ),
    ]
