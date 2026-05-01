"""
Data migration to populate temporal_id on Calendar records and
temporal_month_code on Hebrew Month records, using the TC39 Temporal API identifiers.

Calendar temporal IDs (Temporal calendar identifier):
  Gregorian → "gregory"
  Hebrew    → "hebrew"
  Hijri     → "islamic"
  Chinese   → "chinese"
  Hindu     → "indian"

Month temporal_month_code is only stored explicitly for Hebrew months, where the
Temporal ordering (Tishrei-first) differs from eolas's ordering (Nisan-first).
For all other calendars, temporal_month_code is derived on read from order_in_calendar
using the formula M{order_in_calendar:02d} (e.g. month 9 → M09).

Hebrew months (Tishrei-first, the ordering Temporal uses):
  Tishrei=M01, Cheshvan=M02, Kislev=M03, Tevet=M04, Shevat=M05,
  Adar(I)=M06, Adar II=M06L, Nisan=M07, Iyar=M08, Sivan=M09,
  Tammuz=M10, Av=M11, Elul=M12
"""

from django.db import migrations


# Mapping: canonical calendar name (case-insensitive) → Temporal calendar ID
CALENDAR_TEMPORAL_IDS = {
    'gregorian': 'gregory',
    'hebrew': 'hebrew',
    'hijri': 'islamic',
    'chinese': 'chinese',
    'hindu': 'indian',
}

# Hebrew month names → Temporal monthCode (Tishrei-first / Temporal ordering)
# Only Hebrew needs explicit codes — all other calendars match order_in_calendar.
HEBREW_MONTH_CODES = {
    'tishrei': 'M01',
    'cheshvan': 'M02',
    'kislev': 'M03',
    'tevet': 'M04',
    'shevat': 'M05',
    'adar': 'M06',      # Adar in a non-leap year, or Adar I in a leap year
    'adar i': 'M06',
    'adar ii': 'M06L',
    'nisan': 'M07',
    'iyar': 'M08',
    'sivan': 'M09',
    'tammuz': 'M10',
    'av': 'M11',
    'elul': 'M12',
}


def populate_temporal_ids(apps, schema_editor):
    Calendar = apps.get_model('metadata', 'Calendar')
    Month = apps.get_model('metadata', 'Month')

    # Set temporal_id on Calendar records
    for calendar in Calendar.objects.all():
        temporal_id = CALENDAR_TEMPORAL_IDS.get(calendar.name.lower())
        if temporal_id:
            calendar.temporal_id = temporal_id
            calendar.save(update_fields=['temporal_id'])

    # Set temporal_month_code only for Hebrew months (where Temporal's Tishrei-first
    # ordering differs from eolas's Nisan-first order_in_calendar).
    # For all other calendars, Month.to_json() derives temporal_month_code from
    # order_in_calendar on read, so no DB value is needed.
    for calendar in Calendar.objects.filter(name__iexact='hebrew'):
        for month in Month.objects.filter(calendar=calendar):
            code = HEBREW_MONTH_CODES.get(month.name.lower())
            if code:
                month.temporal_month_code = code
                month.save(update_fields=['temporal_month_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('metadata', '0045_calendar_temporal_id_month_temporal_month_code'),
    ]

    operations = [
        migrations.RunPython(populate_temporal_ids, migrations.RunPython.noop),
    ]
