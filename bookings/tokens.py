"""
Signed links for a booking's receipt and calendar file. Anyone can guess at booking numbers, so
these files also need a token that only our server can make. Tokens don't expire.
"""
from django.core.signing import Signer
from django.urls import reverse
from django.utils.crypto import constant_time_compare

_signer = Signer(salt='zidicarhire.booking-links')
SESSION_KEY = 'my_bookings'
SESSION_LIMIT = 20


def booking_token(ref):
    return _signer.signature(ref)


def check_token(ref, token):
    return bool(token) and constant_time_compare(str(token), booking_token(ref))


def remember(request, booking):
    """The browser that made a booking can open its receipt without the emailed link."""
    refs = [ref for ref in request.session.get(SESSION_KEY, []) if ref != booking.ref]
    request.session[SESSION_KEY] = (refs + [booking.ref])[-SESSION_LIMIT:]


def can_access(request, booking):
    if request.user.is_authenticated and request.user.is_staff:
        return True
    if booking.ref in request.session.get(SESSION_KEY, []):
        return True
    return check_token(booking.ref, request.GET.get('t'))


def links(booking, absolute=''):
    """URLs for the customer's own copy of the booking, each carrying the signed token."""
    token = booking_token(booking.ref)
    return {
        'detail_url': f'{absolute}{reverse("bookings:detail", args=[booking.ref])}?t={token}',
        'ics_url': f'{absolute}{reverse("bookings:ics", args=[booking.ref])}?t={token}',
        'receipt_url': f'{absolute}{reverse("bookings:receipt_pdf", args=[booking.ref])}?t={token}',
        'receipt_page_url': f'{absolute}{reverse("bookings:receipt", args=[booking.ref])}?t={token}',
    }
