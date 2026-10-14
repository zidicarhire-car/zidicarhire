"""Creates the Nairobi branch and moves every existing car into it."""
from django.db import migrations


def assign_to_nairobi(apps, schema_editor):
    Location = apps.get_model('fleet', 'Location')
    Car = apps.get_model('fleet', 'Car')
    nairobi, _ = Location.objects.get_or_create(
        slug='nairobi',
        defaults={'name': 'Nairobi', 'city': 'Nairobi', 'county': 'Nairobi', 'is_active': True,
                  'display_order': 10, 'latitude': '-1.286389', 'longitude': '36.817223'},
    )
    Car.objects.filter(location__isnull=True).update(location=nairobi)


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0002_locations'),
    ]

    operations = [
        migrations.RunPython(assign_to_nairobi, migrations.RunPython.noop),
    ]
