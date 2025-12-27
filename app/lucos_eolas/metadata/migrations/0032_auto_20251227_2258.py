from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("metadata", "0031_festival_commemorates"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE metadata_historicalevent
                DROP CONSTRAINT metadata_historicalevent_wikipedia_slug_key;
            """,
            reverse_sql="""
                CREATE UNIQUE INDEX metadata_historicalevent_wikipedia_slug_key
                ON metadata_historicalevent (wikipedia_slug);
            """,
        ),
    ]
