import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def populate_transportmode_plural(apps, schema_editor):
    """Backfill the plural field on all existing TransportMode rows.

    Names in production may be stored in any case (historically there was no
    lowercasing on save), so we filter case-insensitively using iexact.
    """
    TransportMode = apps.get_model('metadata', 'TransportMode')

    # Vehicle classes
    vehicle_classes = [
        ('aeroplane', 'aeroplanes'),
        ('automobile', 'automobiles'),
        ('bicycle', 'bicycles'),
        ('boat', 'boats'),
        ('bus', 'buses'),
        ('cab', 'cabs'),
        ('caravan', 'caravans'),
        ('chopper', 'choppers'),
        ('coaster', 'coasters'),
        ('combine', 'combines'),
        ('donkey', 'donkeys'),
        ('flying saucer', 'flying saucers'),
        ('horse', 'horses'),
        ('hot air balloon', 'hot air balloons'),
        ('metro', 'metros'),
        ('monocycle', 'monocycles'),
        ('motorbike', 'motorbikes'),
        ('rocket', 'rockets'),
        ('sled', 'sleds'),
        ('sub', 'subs'),
        ('train', 'trains'),
    ]

    # Activity modes (uncountable — plural same as singular)
    activity_modes = [
        ('ambulation', 'ambulation'),
        ('surfing', 'surfing'),
        ('swimming', 'swimming'),
    ]

    for singular, plural in vehicle_classes + activity_modes:
        updated = TransportMode.objects.filter(name__iexact=singular).update(plural=plural)
        if not updated:
            logger.warning("TransportMode '%s' not found, skipping plural backfill.", singular)

    # Fallback: any row still without a plural gets a generic placeholder so the
    # subsequent AlterField (making plural non-null) doesn't fail.
    remaining = TransportMode.objects.filter(plural__isnull=True)
    for mode in remaining:
        logger.warning(
            "TransportMode '%s' has no plural mapping; using name as fallback.", mode.name
        )
        mode.plural = mode.name.lower() + 's'
        mode.save()


class Migration(migrations.Migration):

    dependencies = [
        ('metadata', '0048_transportmode_plural_vehicle'),
    ]

    operations = [
        migrations.RunPython(populate_transportmode_plural, migrations.RunPython.noop),
    ]
