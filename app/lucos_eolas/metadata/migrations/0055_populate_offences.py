from django.db import migrations


OFFENCES = [
    'Swearing',
    'Slurs',
    'Sacrilege',
    'Violence',
    'War',
    'Lèse-majesté',
    'Jingoism',
    'Smut',
    'Alcohol',
    'Drugs',
    'Kink',
    'Arson',
    'Domestic Abuse',
    'Colonialism',
    'Sexual Assault',
    'Sex Work',
    'Animal Cruelty',
    'Fascism',
    'Self Harm (including suicide)',
    'Gambling',
    'Racism',
    'Religious Discrimination',
    'Sexism',
    'Ableism',
    'Homophobia',
    'Transphobia',
]


def populate_offences(apps, schema_editor):
    Offence = apps.get_model('metadata', 'Offence')
    for name in OFFENCES:
        Offence.objects.create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('metadata', '0054_offence'),
    ]

    operations = [
        migrations.RunPython(populate_offences, migrations.RunPython.noop),
    ]
