"""
Bookings now record the branch, pick-up point and return branch, plus the fees charged.
The old free-text pick-up location is kept by copying it into the new notes field.
"""
import django.db.models.deletion
from django.db import migrations, models


def text_location_to_notes(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    for booking in Booking.objects.exclude(pickup_location=''):
        booking.notes = f'Pick-up location: {booking.pickup_location}'
        booking.save(update_fields=['notes'])


def notes_to_text_location(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    prefix = 'Pick-up location: '
    for booking in Booking.objects.filter(notes__startswith=prefix):
        booking.pickup_location = booking.notes[len(prefix):][:200]
        booking.save(update_fields=['pickup_location'])


def fill_branches(apps, schema_editor):
    """Existing bookings were all collected and returned at their car's branch."""
    Booking = apps.get_model('bookings', 'Booking')
    for booking in Booking.objects.select_related('car'):
        booking.pickup_location_id = booking.car.location_id
        booking.return_location_id = booking.car.location_id
        booking.daily_rate = booking.amount // max(booking.days, 1)
        booking.save(update_fields=['pickup_location', 'return_location', 'daily_rate'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0001_initial'),
        ('fleet', '0004_car_location_required'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='notes',
            field=models.TextField(blank=True, help_text='Flight number, hotel or delivery address, and older free-text pick-up details'),
        ),
        migrations.RunPython(text_location_to_notes, notes_to_text_location),
        migrations.RemoveField(
            model_name='booking',
            name='pickup_location',
        ),
        migrations.AddField(
            model_name='booking',
            name='pickup_location',
            field=models.ForeignKey(help_text='Branch the car is collected from', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='pickup_bookings', to='fleet.location'),
        ),
        migrations.AddField(
            model_name='booking',
            name='pickup_point',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='bookings', to='fleet.pickuppoint'),
        ),
        migrations.AddField(
            model_name='booking',
            name='return_location',
            field=models.ForeignKey(help_text='Branch the car is returned to', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='return_bookings', to='fleet.location'),
        ),
        migrations.AddField(
            model_name='booking',
            name='daily_rate',
            field=models.PositiveIntegerField(default=0, help_text='Price per day in KES at the time of booking'),
        ),
        migrations.AddField(
            model_name='booking',
            name='pickup_fee',
            field=models.PositiveIntegerField(default=0, help_text='Pick-up point fee in KES'),
        ),
        migrations.AddField(
            model_name='booking',
            name='one_way_fee',
            field=models.PositiveIntegerField(default=0, help_text='One-way return fee in KES'),
        ),
        migrations.AddField(
            model_name='booking',
            name='extras_amount',
            field=models.PositiveIntegerField(default=0, help_text='Extras in KES'),
        ),
        migrations.AddField(
            model_name='booking',
            name='car_relocated',
            field=models.BooleanField(default=False, help_text="For one-way hires: the car has arrived and was moved to the return branch"),
        ),
        migrations.RunPython(fill_branches, migrations.RunPython.noop),
    ]
