"""Gives every existing booking a 'Booking made' (and, if paid, a 'Paid') line in its new timeline."""
from django.db import migrations


def backfill(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    BookingEvent = apps.get_model('bookings', 'BookingEvent')
    for booking in Booking.objects.filter(events__isnull=True):
        made = BookingEvent.objects.create(booking=booking, kind='created', message='Booked on the website')
        BookingEvent.objects.filter(pk=made.pk).update(created_at=booking.created_at)
        if booking.paid_at:
            receipt = f'M-Pesa receipt {booking.mpesa_receipt}' if booking.mpesa_receipt else ''
            paid = BookingEvent.objects.create(booking=booking, kind='paid', message=receipt)
            BookingEvent.objects.filter(pk=paid.pk).update(created_at=booking.paid_at)


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0005_picked_up_and_events'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
