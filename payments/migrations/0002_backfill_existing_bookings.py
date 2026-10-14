"""
Existing paid bookings get amount_paid filled in, and every booking that already had an M-Pesa
prompt gets one Payment row, so the payment history isn't empty for older bookings.
"""
from django.db import migrations

PAID = ('paid', 'completed')
TO_PAYMENT_STATUS = {'paid': 'success', 'completed': 'success', 'failed': 'failed', 'cancelled': 'failed'}


def backfill(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    Payment = apps.get_model('payments', 'Payment')
    for booking in Booking.objects.filter(status__in=PAID):
        booking.amount_paid = booking.amount
        booking.save(update_fields=['amount_paid'])
    for booking in Booking.objects.exclude(checkout_request_id='').exclude(payments__isnull=False):
        Payment.objects.create(
            booking=booking, reference=booking.ref, amount=booking.amount, phone=booking.phone,
            payhero_reference=booking.payhero_reference, checkout_request_id=booking.checkout_request_id,
            status=TO_PAYMENT_STATUS.get(booking.status, 'pending'), mpesa_receipt=booking.mpesa_receipt,
            result_desc=booking.result_desc,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
        ('bookings', '0004_booking_amount_paid'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
