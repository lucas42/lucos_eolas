import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def populate_festival_periods(apps, schema_editor):
    Festival = apps.get_model('metadata', 'Festival')
    FestivalPeriod = apps.get_model('metadata', 'FestivalPeriod')
    Month = apps.get_model('metadata', 'Month')

    def get_festival(name):
        try:
            return Festival.objects.get(name=name)
        except Festival.DoesNotExist:
            logger.warning("Festival '%s' not found, skipping its periods.", name)
            return None

    def get_month(name):
        try:
            return Month.objects.get(name=name)
        except Month.DoesNotExist:
            logger.warning("Month '%s' not found, skipping dependent periods.", name)
            return None
        except Month.MultipleObjectsReturned:
            logger.warning("Multiple months named '%s', skipping to avoid ambiguity.", name)
            return None

    # Christmas: two periods covering the whole of December.
    # Build-up is the first half (1st–15th); full Christmas is the second half (16th–31st).
    christmas = get_festival("Christmas")
    december = get_month("December")
    if christmas and december:
        FestivalPeriod.objects.create(
            name="Christmas build-up",
            festival=christmas,
            start_day=1,
            start_month=december,
            duration_days=15,
        )
        FestivalPeriod.objects.create(
            name="Full Christmas",
            festival=christmas,
            start_day=16,
            start_month=december,
            duration_days=16,
        )

    # Chanukah: 8-day festival beginning on 25 Chislev in the Hebrew calendar.
    chanukah = get_festival("Chanukah")
    chislev = get_month("Chislev")
    if chanukah and chislev:
        FestivalPeriod.objects.create(
            name="Chanukah celebration",
            festival=chanukah,
            start_day=25,
            start_month=chislev,
            duration_days=8,
        )

    # Allhalloween: themed music period starting 25th October, running 10 days
    # (to 3rd November), finishing safely before Bonfire Night on 5th November.
    allhalloween = get_festival("Allhalloween")
    october = get_month("October")
    if allhalloween and october:
        FestivalPeriod.objects.create(
            name="Hallowe'en themed music",
            festival=allhalloween,
            start_day=25,
            start_month=october,
            duration_days=10,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('metadata', '0043_festivalperiod'),
    ]

    operations = [
        migrations.RunPython(populate_festival_periods, migrations.RunPython.noop),
    ]
