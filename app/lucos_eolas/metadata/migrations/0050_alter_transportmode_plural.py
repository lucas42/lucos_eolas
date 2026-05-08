import lucos_eolas.metadata.fields
from django.db import migrations


class Migration(migrations.Migration):
    """Make TransportMode.plural non-null and unique.

    This is safe to run after 0049 has backfilled a distinct plural value for
    every existing row.
    """

    dependencies = [
        ('metadata', '0049_populate_transportmode_plural'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transportmode',
            name='plural',
            field=lucos_eolas.metadata.fields.RDFCharField(max_length=255, unique=True, verbose_name='plural'),
        ),
    ]
