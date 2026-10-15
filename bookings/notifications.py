"""Email alerts. Sent directly (PythonAnywhere web apps don't support background threads)."""
import logging

from django.conf import settings
from django.core.mail import EmailMessage, send_mail

logger = logging.getLogger(__name__)


def _send(subject, body, recipients):
    recipients = list(dict.fromkeys(r for r in recipients if r))
    if not recipients:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    except Exception:
        logger.exception('Email failed: %s', subject)


def send_alert(subject, body, recipients):
    """Plain-text alert email to staff; failures are logged, never raised."""
    _send(subject, body, recipients)


def branch_recipients(*locations):
    """ADMIN_NOTIFY_EMAILS plus the alert email of each branch involved."""
    return list(settings.ADMIN_NOTIFY_EMAILS) + [loc.notify_email for loc in locations if loc is not None]


def booking_details(booking):
    city = booking.pickup_location.name if booking.pickup_location_id else 'Not set'
    point = booking.pickup_point.name if booking.pickup_point_id else 'Branch office'
    return_to = (f'{booking.return_location.name} (one-way)' if booking.is_one_way else f'{city} (same branch)')
    lines = '\n'.join(f'  {line["label"]}: KES {line["amount"]:,}' for line in booking.price_lines()
                      if not line.get('total'))
    return (
        f'Booking: {booking.ref}\n'
        f'Car: {booking.car.name}\n'
        f'City: {city}\n'
        f'Pick-up point: {point}\n'
        f'Return to: {return_to}\n'
        f'Pick-up: {booking.pickup_date:%a %d %b %Y} at {booking.pickup_time:%H:%M}\n'
        f'Return: {booking.return_date:%a %d %b %Y} at {booking.return_time:%H:%M} '
        f'({booking.days} day{"s" if booking.days != 1 else ""})\n'
        + (f'Notes: {booking.notes}\n' if booking.notes else '')
        + f'Price:\n{lines}\n'
        f'Amount paid: KES {booking.amount_paid or booking.amount:,}\n'
        + (f'Balance due at pick-up: KES {booking.balance:,}\n' if booking.balance > 0 else '')
        + f'M-Pesa receipt: {booking.mpesa_receipt or "-"}\n'
    )


def notify_booking_paid(booking):
    car = booking.car
    details = booking_details(booking)
    city = booking.pickup_location.name if booking.pickup_location_id else ''
    point = f', {booking.pickup_point.name}' if booking.pickup_point_id else ''

    _send(
        f'New paid booking {booking.ref}: {car.name} ({city}{point})',
        'A car has just been booked and paid for.\n\n'
        f'Customer: {booking.customer_name}\n'
        f'Phone: {booking.local_phone}\n'
        f'Email: {booking.email or "Not given"}\n\n'
        + details
        + (f'\nThis is a one-way hire. The car stays listed in {city} until you move it to '
           f'{booking.return_location.name} in the dashboard once it arrives.\n' if booking.is_one_way else '')
        + f'\nOpen the dashboard: {settings.SITE_URL}/dashboard/\n',
        branch_recipients(booking.pickup_location, booking.return_location if booking.is_one_way else None),
    )

    if booking.email:
        send_customer_confirmation(booking)


def send_customer_confirmation(booking):
    """The customer's confirmation with the PDF receipt attached. Returns True if it was sent."""
    from .receipts import build_pdf
    from .tokens import links

    if not booking.email:
        return False
    biz = settings.BUSINESS
    phone = booking.pickup_location.contact_phone if booking.pickup_location_id else biz['phone']
    urls = links(booking, absolute=settings.SITE_URL)
    message = EmailMessage(
        f'Your {biz["name"]} booking {booking.ref} is confirmed',
        f'Hi {booking.customer_name},\n\n'
        'Thanks for booking with us. Your payment was received and the car is reserved for you.\n'
        'Bring your ID or passport and your driving licence when you collect it.\n\n'
        + booking_details(booking)
        + f'\nYour receipt is attached. You can also download it here: {urls["receipt_url"]}\n'
        f'View your booking: {urls["detail_url"]}\n'
        f'Add it to your calendar: {urls["ics_url"]}\n\n'
        f'Questions? Call {phone} or reply to this email.\n\n{biz["name"]}\n',
        settings.DEFAULT_FROM_EMAIL,
        [booking.email],
    )
    try:
        message.attach(f'{biz["name"]}-receipt-{booking.ref}.pdf', build_pdf(booking), 'application/pdf')
        message.send(fail_silently=False)
    except Exception:
        logger.exception('Confirmation email failed for %s', booking.ref)
        return False
    return True


def notify_new_chat(conversation, first_message):
    city = conversation.location.name if conversation.location_id else 'No city chosen'
    _send(
        f'New chat from {conversation.name} ({city})',
        f'{conversation.name} ({conversation.contact or "no contact given"}) wrote:\n\n'
        f'"{first_message}"\n\n'
        f'City: {city}\n\n'
        f'Reply in the dashboard: {settings.SITE_URL}/dashboard/chats/?c={conversation.id}\n',
        branch_recipients(conversation.location),
    )



def notify_agent_request(conversation, reason=''):
    """A visitor in the chat wants a person (asked for one, or the assistant couldn't help)."""
    city = conversation.location.name if conversation.location_id else 'No city chosen'
    _send(
        f'Chat: {conversation.name} wants to talk to a person ({city})',
        f'{conversation.name} ({conversation.contact or "no contact given"}) is waiting for a team member in the '
        'website chat.\n\n'
        + (f'Last message: "{reason}"\n\n' if reason else '')
        + f'City: {city}\n\n'
        f'Reply in the dashboard: {settings.SITE_URL}/dashboard/chats/?c={conversation.id}\n',
        branch_recipients(conversation.location),
    )
